import unittest
import torch
import os
import tempfile
from pathlib import Path
from .io_interceptor import TorchIOInterceptor
import threading
import signal
import time
import pickle

class TestTorchIOInterceptor(unittest.TestCase):
    def setUp(self):
        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.whitelist_dir = os.path.join(self.test_dir, "whitelist")
        self.non_whitelist_dir = os.path.join(self.test_dir, "non_whitelist")
        
        # Create directories
        os.makedirs(self.whitelist_dir, exist_ok=True)
        os.makedirs(self.non_whitelist_dir, exist_ok=True)
        
        # Create a simple model for testing
        self.test_model = torch.nn.Linear(10, 2)
    
    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_whitelist_save(self):
        """Test saving to whitelisted path."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        save_path = os.path.join(self.whitelist_dir, "model.pt")
        with interceptor.activate():
            torch.save(self.test_model.state_dict(), save_path)
        
        self.assertTrue(os.path.exists(save_path))
        self.assertFalse(os.path.exists(save_path + ".hash"))
        
        # Verify we can load the model
        loaded_state = torch.load(save_path)
        self.assertEqual(len(loaded_state), len(self.test_model.state_dict()))
    
    def test_encrypt_non_whitelist(self):
        """Test encrypting saves to non-whitelisted path."""
        interceptor = TorchIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "model.pt")
        with interceptor.activate():
            torch.save(self.test_model.state_dict(), save_path)
        
        # Original file should not exist, but hashed file should
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))
        
        # Verify hash
        is_match = interceptor.verify_hash(self.test_model.state_dict(), save_path + ".hash")
        self.assertTrue(is_match)
    
    def test_ignore_non_whitelist(self):
        """Test ignoring saves to non-whitelisted path."""
        interceptor = TorchIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="ignore"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "model.pt")
        with interceptor.activate():
            torch.save(self.test_model.state_dict(), save_path)
        
        # Neither original nor hashed file should exist
        self.assertFalse(os.path.exists(save_path))
        self.assertFalse(os.path.exists(save_path + ".hash"))
    
    def test_error_handling(self):
        """Test error handling and function restoration."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = torch.save
        
        try:
            with interceptor.activate():
                # Simulate an error during save
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass
        
        # Verify torch.save is restored after error
        self.assertEqual(torch.save, original_save)
    
    def test_usage_outside_context(self):
        """Test that save operations fail outside context manager."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        save_path = os.path.join(self.whitelist_dir, "model.pt")
        
        # Should raise error when used outside context
        with self.assertRaises(RuntimeError):
            interceptor._intercepted_save(self.test_model.state_dict(), save_path)
    
    def test_distributed_save(self):
        """Test saving in a distributed setting."""
        if not torch.distributed.is_available():
            self.skipTest("Distributed not available")
        
        # Initialize distributed environment
        torch.distributed.init_process_group(
            backend='gloo',
            init_method='tcp://localhost:23456',
            world_size=2,
            rank=0
        )
        
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        save_path = os.path.join(self.whitelist_dir, "dist_model.pt")
        with interceptor.activate():
            torch.save(self.test_model.state_dict(), save_path)
        
        # Only rank 0 should create the file
        if torch.distributed.get_rank() == 0:
            self.assertTrue(os.path.exists(save_path))
        
        torch.distributed.destroy_process_group()

    def test_jit_save(self):
        """Test intercepting torch.jit.save."""
        model = torch.jit.script(self.test_model)
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        save_path = os.path.join(self.whitelist_dir, "model.pt")
        with interceptor.activate():
            torch.jit.save(model, save_path)
        
        self.assertTrue(os.path.exists(save_path))

    def test_state_dict_save(self):
        """Test intercepting state_dict save."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        save_path = os.path.join(self.whitelist_dir, "state_dict.pt")
        with interceptor.activate():
            torch.save(self.test_model.state_dict(), save_path)
        
        self.assertTrue(os.path.exists(save_path))

    def test_nested_context(self):
        """Test nested context manager usage."""
        interceptor1 = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        interceptor2 = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = torch.save
        
        with interceptor1.activate():
            with interceptor2.activate():
                torch.save(self.test_model.state_dict(), 
                          os.path.join(self.whitelist_dir, "model.pt"))
        
        self.assertEqual(torch.save, original_save)
        self.assertFalse(interceptor1._is_active)
        self.assertFalse(interceptor2._is_active)

    def test_temporary_file_cleanup(self):
        """Test that temporary files are cleaned up after interrupts."""
        interceptor = TorchIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        temp_files_before = set(os.listdir(tempfile.gettempdir()))
        
        try:
            with interceptor.activate():
                with self.assertRaises(RuntimeError):
                    torch.save(self.test_model.state_dict(), 
                             os.path.join(self.non_whitelist_dir, "model.pt"))
                    raise RuntimeError("Simulated error during save")
        except RuntimeError:
            pass
        
        temp_files_after = set(os.listdir(tempfile.gettempdir()))
        self.assertEqual(temp_files_before, temp_files_after)

    def test_concurrent_saves(self):
        """Test concurrent save operations."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        def save_function(path):
            torch.save(self.test_model.state_dict(), path)
        
        with interceptor.activate():
            threads = []
            for i in range(5):
                path = os.path.join(self.whitelist_dir, f"model_{i}.pt")
                thread = threading.Thread(target=save_function, args=(path,))
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
        
        for i in range(5):
            self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, f"model_{i}.pt")))

    def test_interrupt_handling(self):
        """Test that functions are restored after interrupt."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = torch.save
        
        def interrupt_thread():
            time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGINT)
        
        try:
            thread = threading.Thread(target=interrupt_thread)
            thread.start()
            
            try:
                with interceptor.activate():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            
            self.assertEqual(torch.save, original_save)
            self.assertFalse(interceptor._is_active)
        finally:
            signal.signal(signal.SIGINT, signal.default_int_handler)

    def test_system_exit_handling(self):
        """Test that functions are restored after system exit."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = torch.save
        
        try:
            with interceptor.activate():
                raise SystemExit()
        except SystemExit:
            pass
        
        self.assertEqual(torch.save, original_save)
        self.assertFalse(interceptor._is_active)

    def test_pickle_save(self):
        """Test intercepting pickle.dump saves."""
        interceptor = TorchIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted path
        save_path = os.path.join(self.whitelist_dir, "model.pkl")
        with interceptor.activate():
            with open(save_path, 'wb') as f:
                pickle.dump(self.test_model.state_dict(), f)
        
        self.assertTrue(os.path.exists(save_path))
        
        # Test non-whitelisted path with encryption
        interceptor = TorchIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        save_path = os.path.join(self.non_whitelist_dir, "model.pkl")
        with interceptor.activate():
            with open(save_path, 'wb') as f:
                pickle.dump(self.test_model.state_dict(), f)
        
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))

if __name__ == '__main__':
    unittest.main() 