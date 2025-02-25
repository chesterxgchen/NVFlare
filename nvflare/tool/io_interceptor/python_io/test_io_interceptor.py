import unittest
import os
import tempfile
import numpy as np
import torch
import tensorflow as tf
from pathlib import Path
from .io_interceptor import PythonIOInterceptor
import signal
import threading
import time
import psutil
import mmap

class TestPythonIOInterceptor(unittest.TestCase):
    def setUp(self):
        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.whitelist_dir = os.path.join(self.test_dir, "whitelist")
        self.non_whitelist_dir = os.path.join(self.test_dir, "non_whitelist")
        
        # Create directories
        os.makedirs(self.whitelist_dir, exist_ok=True)
        os.makedirs(self.non_whitelist_dir, exist_ok=True)
        
        # Create test data
        self.test_text = "Hello, World!"
        self.test_bytes = b"Binary Data"
        self.test_numpy = np.array([1, 2, 3, 4, 5])
        self.test_torch_tensor = torch.tensor([1., 2., 3.])
        self.test_tf_model = tf.keras.Sequential([tf.keras.layers.Dense(1)])
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_text_file_write(self):
        """Test basic text file writing."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted path
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "test.txt"), "w") as f:
                f.write(self.test_text)
        
        # Verify file was written
        with open(os.path.join(self.whitelist_dir, "test.txt"), "r") as f:
            self.assertEqual(f.read(), self.test_text)
        
        # Test non-whitelisted path with encryption
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "test.txt"), "w") as f:
                f.write(self.test_text)
        
        # Verify hash file exists and original doesn't
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "test.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "test.txt.hash")))
    
    def test_binary_file_write(self):
        """Test binary file writing."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "test.bin"), "wb") as f:
                f.write(self.test_bytes)
        
        with open(os.path.join(self.whitelist_dir, "test.bin"), "rb") as f:
            self.assertEqual(f.read(), self.test_bytes)
    
    def test_numpy_save(self):
        """Test NumPy array saving."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            np.save(os.path.join(self.whitelist_dir, "test.npy"), self.test_numpy)
            np.save(os.path.join(self.non_whitelist_dir, "test.npy"), self.test_numpy)
        
        # Verify whitelisted save worked
        loaded = np.load(os.path.join(self.whitelist_dir, "test.npy"))
        np.testing.assert_array_equal(loaded, self.test_numpy)
        
        # Verify non-whitelisted was hashed
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "test.npy")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "test.npy.hash")))
    
    def test_torch_save(self):
        """Test PyTorch tensor saving."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            torch.save(self.test_torch_tensor, os.path.join(self.whitelist_dir, "test.pt"))
            torch.save(self.test_torch_tensor, os.path.join(self.non_whitelist_dir, "test.pt"))
        
        # Verify whitelisted save worked
        loaded = torch.load(os.path.join(self.whitelist_dir, "test.pt"))
        self.assertTrue(torch.equal(loaded, self.test_torch_tensor))
        
        # Verify non-whitelisted was hashed
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "test.pt.hash")))
    
    def test_tensorflow_save(self):
        """Test TensorFlow model saving."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            self.test_tf_model.save(os.path.join(self.whitelist_dir, "test_model"))
            self.test_tf_model.save(os.path.join(self.non_whitelist_dir, "test_model"))
        
        # Verify whitelisted save worked
        tf.keras.models.load_model(os.path.join(self.whitelist_dir, "test_model"))
        
        # Verify non-whitelisted was hashed
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "test_model.hash")))
    
    def test_append_mode(self):
        """Test append mode writing."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Write initial content
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "test.txt"), "w") as f:
                f.write("Initial")
            
            # Append content
            with open(os.path.join(self.whitelist_dir, "test.txt"), "a") as f:
                f.write(" Appended")
        
        # Verify combined content
        with open(os.path.join(self.whitelist_dir, "test.txt"), "r") as f:
            self.assertEqual(f.read(), "Initial Appended")
    
    def test_interrupt_handling(self):
        """Test handling of interrupts during file operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_open = builtins.open
        
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
            
            # Verify open is restored
            self.assertEqual(builtins.open, original_open)
            self.assertFalse(interceptor._is_active)
        finally:
            signal.signal(signal.SIGINT, signal.default_int_handler)
    
    def test_verify_hash(self):
        """Test hash verification."""
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        test_data = "Test Data"
        filepath = os.path.join(self.non_whitelist_dir, "test.txt")
        
        with interceptor.activate():
            with open(filepath, "w") as f:
                f.write(test_data)
        
        # Verify the hash matches
        self.assertTrue(interceptor.verify_hash(test_data, filepath + ".hash"))
        self.assertFalse(interceptor.verify_hash("Wrong Data", filepath + ".hash"))

    def test_nested_writes(self):
        """Test nested file writes."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Create a file that writes to another file
            with open(os.path.join(self.whitelist_dir, "main.txt"), "w") as f1:
                f1.write("Main file")
                with open(os.path.join(self.non_whitelist_dir, "nested.txt"), "w") as f2:
                    f2.write("Nested file")
        
        # Verify main file exists and nested is hashed
        self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "main.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "nested.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "nested.txt.hash")))

    def test_multiple_interceptors(self):
        """Test multiple interceptors working together."""
        interceptor1 = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        interceptor2 = PythonIOInterceptor(
            whitelist_paths=[self.non_whitelist_dir],
            non_whitelist_action="ignore"
        )
        
        filepath = os.path.join(self.test_dir, "test.txt")
        
        # Test with both interceptors active
        with interceptor1.activate():
            with interceptor2.activate():
                with open(filepath, "w") as f:
                    f.write("Test")
        
        # File should be hashed (interceptor1's action) not ignored (interceptor2's action)
        self.assertFalse(os.path.exists(filepath))
        self.assertTrue(os.path.exists(filepath + ".hash"))

    def test_large_file_handling(self):
        """Test handling of large file writes."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        large_data = b"0" * (10 * 1024 * 1024)  # 10MB of data
        
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "large.bin"), "wb") as f:
                f.write(large_data)
        
        # Verify hash file exists and is of reasonable size
        hash_path = os.path.join(self.non_whitelist_dir, "large.bin.hash")
        self.assertTrue(os.path.exists(hash_path))
        self.assertLess(os.path.getsize(hash_path), len(large_data))

    def test_concurrent_writes(self):
        """Test concurrent file writes."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        def write_file(index):
            with open(os.path.join(self.non_whitelist_dir, f"file_{index}.txt"), "w") as f:
                f.write(f"Content {index}")
        
        with interceptor.activate():
            threads = []
            for i in range(10):
                thread = threading.Thread(target=write_file, args=(i,))
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
        
        # Verify all files were hashed
        for i in range(10):
            self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, f"file_{i}.txt")))
            self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, f"file_{i}.txt.hash")))

    def test_directory_creation(self):
        """Test file writes with directory creation."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        nested_path = os.path.join(self.non_whitelist_dir, "nested", "deep", "file.txt")
        
        with interceptor.activate():
            os.makedirs(os.path.dirname(nested_path), exist_ok=True)
            with open(nested_path, "w") as f:
                f.write("Test")
        
        # Verify directories were created but file was hashed
        self.assertTrue(os.path.exists(os.path.dirname(nested_path)))
        self.assertFalse(os.path.exists(nested_path))
        self.assertTrue(os.path.exists(nested_path + ".hash"))

    def test_streaming_large_file(self):
        """Test handling of streaming large file writes."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        chunk_size = 1024 * 1024  # 1MB chunks
        total_size = 100 * chunk_size  # 100MB total
        
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "large_stream.bin"), "wb") as f:
                # Write in chunks to simulate streaming
                for _ in range(100):
                    f.write(b"0" * chunk_size)
        
        # Verify hash file exists and memory usage was reasonable
        hash_path = os.path.join(self.non_whitelist_dir, "large_stream.bin.hash")
        self.assertTrue(os.path.exists(hash_path))
        
        # Get process memory info
        process = psutil.Process()
        mem_info = process.memory_info()
        
        # Memory usage should be much less than file size
        self.assertLess(mem_info.rss - process.parent().memory_info().rss, total_size / 10)

    def test_temp_file_security(self):
        """Test security of temporary files."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        temp_dir = tempfile.gettempdir()
        initial_temp_files = set(os.listdir(temp_dir))
        
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "secret.txt"), "w") as f:
                f.write("sensitive data")
                
                # Try to find and read temp file during write
                current_temp_files = set(os.listdir(temp_dir))
                new_temp_files = current_temp_files - initial_temp_files
                
                if new_temp_files:  # If we found the temp file
                    temp_path = os.path.join(temp_dir, list(new_temp_files)[0])
                    with open(temp_path, 'rb') as tf:
                        temp_content = tf.read()
                        # Content should be encrypted
                        self.assertNotIn(b"sensitive data", temp_content)
        
        # After close, temp file should be securely deleted
        final_temp_files = set(os.listdir(temp_dir))
        self.assertEqual(initial_temp_files, final_temp_files)

    def test_memory_cleanup(self):
        """Test that sensitive data is cleared from memory."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "secret.txt"), "w") as f:
                f.write("sensitive data")
                # Get intercepted file object
                intercepted_file = f
                
                # Verify encryption key exists during operation
                self.assertIsNotNone(intercepted_file._temp_key)
            
            # After close, sensitive data should be cleared
            self.assertIsNone(intercepted_file._temp_key)
            self.assertIsNone(intercepted_file._cipher)
            self.assertIsNone(intercepted_file._buffer)

    def test_memory_threshold_behavior(self):
        """Test that memory threshold controls temp file usage."""
        small_threshold = 1024  # 1KB for testing
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=small_threshold
        )
        
        # Test file smaller than threshold
        small_data = b"0" * (small_threshold - 100)  # Just under threshold
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "small.bin"), "wb") as f:
                f.write(small_data)
                # Verify using memory buffer
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
                self.assertIsNone(f._temp_path)
        
        # Test file larger than threshold
        large_data = b"0" * (small_threshold + 100)  # Just over threshold
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "large.bin"), "wb") as f:
                f.write(large_data)
                # Verify switched to temp file
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
                self.assertIsNotNone(f._temp_path)

    def test_default_threshold(self):
        """Test the default 400MB threshold behavior."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test with 300MB (should use memory)
        size_300mb = 300 * 1024 * 1024
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "300mb.bin"), "wb") as f:
                f.write(b"0" * size_300mb)
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
        
        # Skip 500MB test if not enough memory
        import psutil
        if psutil.virtual_memory().available > 600 * 1024 * 1024:  # Check if we have enough memory
            # Test with 500MB (should use temp file)
            size_500mb = 500 * 1024 * 1024
            with interceptor.activate():
                with open(os.path.join(self.whitelist_dir, "500mb.bin"), "wb") as f:
                    f.write(b"0" * size_500mb)
                    self.assertTrue(f._using_temp_file)
                    self.assertIsNone(f._buffer)

    def test_incremental_write_threshold(self):
        """Test threshold behavior with incremental writes."""
        threshold = 1024  # 1KB for testing
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=threshold
        )
        
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "incremental.bin"), "wb") as f:
                # Write 500 bytes (under threshold)
                f.write(b"0" * 500)
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
                
                # Write another 600 bytes (now over threshold)
                f.write(b"0" * 600)
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
                
                # Verify final file is correct size
                f.close()
                size = os.path.getsize(os.path.join(self.whitelist_dir, "incremental.bin"))
                self.assertEqual(size, 1100)

    def test_threshold_with_encryption(self):
        """Test memory threshold behavior with encryption."""
        threshold = 1024  # 1KB for testing
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=threshold,
            non_whitelist_action="encrypt"
        )
        
        # Test large file in non-whitelisted path
        large_data = b"0" * (threshold + 100)
        with interceptor.activate():
            with open(os.path.join(self.non_whitelist_dir, "large.bin"), "wb") as f:
                f.write(large_data)
                # Verify using temp file
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
                
                # Verify temp file is encrypted
                if f._temp_path:
                    with open(f._temp_path, 'rb') as temp:
                        temp_content = temp.read()
                        # Content should be encrypted
                        self.assertNotEqual(temp_content, large_data)
        
        # Verify final hash file exists
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "large.bin.hash")))

    def test_pytorch_model_handling(self):
        """Test handling of PyTorch model saves."""
        # Create a small model
        small_model = torch.nn.Linear(10, 2)
        
        # Create a large model
        large_model = torch.nn.Sequential(*[
            torch.nn.Linear(1000, 1000) for _ in range(100)
        ])
        
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=1024 * 1024  # 1MB threshold for testing
        )
        
        # Test small model (should use memory)
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "small_model.pt"), "wb") as f:
                torch.save(small_model, f)
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
        
        # Test large model (should use temp file)
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "large_model.pt"), "wb") as f:
                torch.save(large_model, f)
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
        
        # Test non-whitelisted save with encryption
        with interceptor.activate():
            torch.save(small_model, os.path.join(self.non_whitelist_dir, "model.pt"))
        
        # Verify hash file exists
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "model.pt")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "model.pt.hash")))
        
        # Verify model can be loaded from whitelisted path
        loaded_model = torch.load(os.path.join(self.whitelist_dir, "small_model.pt"))
        self.assertEqual(
            sum(p.numel() for p in loaded_model.parameters()),
            sum(p.numel() for p in small_model.parameters())
        )

    def test_pytorch_lightning_handling(self):
        """Test handling of PyTorch Lightning model saves."""
        try:
            import pytorch_lightning as pl
            from pytorch_lightning.callbacks import ModelCheckpoint
        except ImportError:
            self.skipTest("PyTorch Lightning not installed")

        class SimpleModel(pl.LightningModule):
            def __init__(self):
                super().__init__()
                self.layer = torch.nn.Linear(10, 2)
                
            def forward(self, x):
                return self.layer(x)
                
            def training_step(self, batch, batch_idx):
                return torch.tensor(0.0)
                
            def configure_optimizers(self):
                return torch.optim.Adam(self.parameters())

        # Create model and trainer with checkpoint callback
        model = SimpleModel()
        checkpoint_callback = ModelCheckpoint(
            dirpath=self.whitelist_dir,
            filename='model-{epoch}',
            save_top_k=1
        )
        
        trainer = pl.Trainer(
            max_epochs=1,
            callbacks=[checkpoint_callback],
            default_root_dir=self.whitelist_dir
        )

        # Test whitelisted path
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        with interceptor.activate():
            # This will trigger saves through callbacks
            trainer.fit(model, torch.utils.data.DataLoader([torch.randn(10)]))
            
            # Verify checkpoint was saved
            self.assertTrue(os.path.exists(checkpoint_callback.best_model_path))

        # Test non-whitelisted path
        checkpoint_callback_non_white = ModelCheckpoint(
            dirpath=self.non_whitelist_dir,
            filename='model-{epoch}',
            save_top_k=1
        )
        
        trainer_non_white = pl.Trainer(
            max_epochs=1,
            callbacks=[checkpoint_callback_non_white],
            default_root_dir=self.non_whitelist_dir
        )

        with interceptor.activate():
            trainer_non_white.fit(model, torch.utils.data.DataLoader([torch.randn(10)]))
            
            # Verify checkpoint was hashed
            expected_path = os.path.join(self.non_whitelist_dir, "model-epoch=0.ckpt")
            self.assertFalse(os.path.exists(expected_path))
            self.assertTrue(os.path.exists(expected_path + ".hash"))

    def test_huggingface_model_handling(self):
        """Test handling of HuggingFace model saves."""
        try:
            from transformers import BertConfig, BertModel
        except ImportError:
            self.skipTest("HuggingFace transformers not installed")

        # Create a small BERT model
        config = BertConfig(
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=2,
            intermediate_size=64
        )
        model = BertModel(config)

        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted save
        with interceptor.activate():
            model.save_pretrained(self.whitelist_dir)
            # Verify model files exist
            self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "config.json")))
            self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "pytorch_model.bin")))

        # Test non-whitelisted save
        with interceptor.activate():
            model.save_pretrained(self.non_whitelist_dir)
            # Verify files were hashed
            self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "pytorch_model.bin")))
            self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "pytorch_model.bin.hash")))

    def test_fastai_model_handling(self):
        """Test handling of FastAI model saves."""
        try:
            from fastai.data.block import DataBlock, CategoryBlock
            from fastai.tabular.learner import tabular_learner
        except ImportError:
            self.skipTest("FastAI not installed")

        # Create a simple learner
        data = DataBlock(
            blocks=(CategoryBlock, CategoryBlock),
            get_x=lambda x: x
        ).dataloaders([1,2,3])
        
        learn = tabular_learner(data, layers=[10,2])
        
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted save
        with interceptor.activate():
            learn.save(os.path.join(self.whitelist_dir, 'model'))
            self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, 'model.pth')))

        # Test non-whitelisted save
        with interceptor.activate():
            learn.save(os.path.join(self.non_whitelist_dir, 'model'))
            self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, 'model.pth')))
            self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, 'model.pth.hash')))

    def test_distributed_pytorch_handling(self):
        """Test handling of distributed PyTorch saves."""
        if not torch.distributed.is_available():
            self.skipTest("PyTorch distributed not available")
        
        try:
            # Initialize distributed environment
            torch.distributed.init_process_group(
                backend='gloo',
                init_method='tcp://localhost:23456',
                world_size=1,
                rank=0
            )
            
            # Create a model
            model = torch.nn.Linear(10, 2)
            
            # Wrap model in DistributedDataParallel
            ddp_model = torch.nn.parallel.DistributedDataParallel(model)
            
            interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
            
            # Test whitelisted path
            with interceptor.activate():
                # Test direct save
                torch.save(ddp_model.state_dict(), os.path.join(self.whitelist_dir, "ddp_model.pt"))
                
                # Test distributed save wrapper
                if torch.distributed.get_rank() == 0:
                    torch.save(ddp_model.module.state_dict(), os.path.join(self.whitelist_dir, "ddp_model_rank0.pt"))
            
            # Verify only rank 0 created the files
            if torch.distributed.get_rank() == 0:
                self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "ddp_model.pt")))
                self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "ddp_model_rank0.pt")))
            else:
                self.assertFalse(os.path.exists(os.path.join(self.whitelist_dir, "ddp_model.pt")))
                self.assertFalse(os.path.exists(os.path.join(self.whitelist_dir, "ddp_model_rank0.pt")))
            
            # Test non-whitelisted path
            with interceptor.activate():
                if torch.distributed.get_rank() == 0:
                    torch.save(ddp_model.state_dict(), os.path.join(self.non_whitelist_dir, "ddp_model.pt"))
            
            # Verify hash file exists only for rank 0
            if torch.distributed.get_rank() == 0:
                self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "ddp_model.pt")))
                self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "ddp_model.pt.hash")))
            
        finally:
            if torch.distributed.is_initialized():
                torch.distributed.destroy_process_group()

    def test_distributed_pytorch_lightning(self):
        """Test handling of distributed PyTorch Lightning saves."""
        try:
            import pytorch_lightning as pl
            from pytorch_lightning.strategies import DDPStrategy
        except ImportError:
            self.skipTest("PyTorch Lightning not installed")
        
        if not torch.distributed.is_available():
            self.skipTest("PyTorch distributed not available")
        
        class SimpleModel(pl.LightningModule):
            def __init__(self):
                super().__init__()
                self.layer = torch.nn.Linear(10, 2)
            
            def forward(self, x):
                return self.layer(x)
            
            def training_step(self, batch, batch_idx):
                return torch.tensor(0.0)
            
            def configure_optimizers(self):
                return torch.optim.Adam(self.parameters())
        
        # Create model and trainer with DDP strategy
        model = SimpleModel()
        checkpoint_callback = pl.callbacks.ModelCheckpoint(
            dirpath=self.whitelist_dir,
            filename='ddp-model-{epoch}',
            save_top_k=1
        )
        
        trainer = pl.Trainer(
            max_epochs=1,
            strategy=DDPStrategy(find_unused_parameters=False),
            accelerator='cpu',
            devices=2,
            callbacks=[checkpoint_callback]
        )
        
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted path
        with interceptor.activate():
            trainer.fit(model, torch.utils.data.DataLoader([torch.randn(10)]))
            
            # Verify checkpoint was saved (only on rank 0)
            if trainer.is_global_zero:
                self.assertTrue(os.path.exists(checkpoint_callback.best_model_path))
        
        # Test non-whitelisted path
        checkpoint_callback_non_white = pl.callbacks.ModelCheckpoint(
            dirpath=self.non_whitelist_dir,
            filename='ddp-model-{epoch}',
            save_top_k=1
        )
        
        trainer_non_white = pl.Trainer(
            max_epochs=1,
            strategy=DDPStrategy(find_unused_parameters=False),
            accelerator='cpu',
            devices=2,
            callbacks=[checkpoint_callback_non_white]
        )
        
        with interceptor.activate():
            trainer_non_white.fit(model, torch.utils.data.DataLoader([torch.randn(10)]))
            
            # Verify hash file exists only on rank 0
            if trainer_non_white.is_global_zero:
                expected_path = os.path.join(self.non_whitelist_dir, "ddp-model-epoch=0.ckpt")
                self.assertFalse(os.path.exists(expected_path))
                self.assertTrue(os.path.exists(expected_path + ".hash"))

    def test_numpy_array_handling(self):
        """Test handling of NumPy array saves."""
        # Create arrays of different sizes
        small_array = np.random.rand(100, 100)  # Small array
        large_array = np.random.rand(5000, 5000)  # Large array ~200MB
        
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=1024 * 1024  # 1MB threshold for testing
        )
        
        # Test small array (should use memory)
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "small_array.npy"), "wb") as f:
                np.save(f, small_array)
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
        
        # Test large array (should use temp file)
        with interceptor.activate():
            with open(os.path.join(self.whitelist_dir, "large_array.npy"), "wb") as f:
                np.save(f, large_array)
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
        
        # Test non-whitelisted save with encryption
        with interceptor.activate():
            np.save(os.path.join(self.non_whitelist_dir, "array.npy"), small_array)
        
        # Verify hash file exists
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "array.npy")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "array.npy.hash")))
        
        # Verify array can be loaded from whitelisted path
        loaded_array = np.load(os.path.join(self.whitelist_dir, "small_array.npy"))
        np.testing.assert_array_equal(loaded_array, small_array)

    def test_tensorflow_model_handling(self):
        """Test handling of TensorFlow model saves."""
        # Create models of different sizes
        small_model = tf.keras.Sequential([
            tf.keras.layers.Dense(10, input_shape=(5,)),
            tf.keras.layers.Dense(2)
        ])
        
        large_model = tf.keras.Sequential([
            tf.keras.layers.Dense(1000, input_shape=(1000,)),
            *[tf.keras.layers.Dense(1000) for _ in range(50)]
        ])
        
        interceptor = PythonIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            memory_threshold=1024 * 1024  # 1MB threshold for testing
        )
        
        # Test small model (should use memory)
        with interceptor.activate():
            small_model.save(os.path.join(self.whitelist_dir, "small_model"))
            # Check the main model file
            with open(os.path.join(self.whitelist_dir, "small_model", "saved_model.pb"), "rb") as f:
                self.assertFalse(f._using_temp_file)
                self.assertIsNotNone(f._buffer)
        
        # Test large model (should use temp file)
        with interceptor.activate():
            large_model.save(os.path.join(self.whitelist_dir, "large_model"))
            # Check the main model file
            with open(os.path.join(self.whitelist_dir, "large_model", "saved_model.pb"), "rb") as f:
                self.assertTrue(f._using_temp_file)
                self.assertIsNone(f._buffer)
        
        # Test non-whitelisted save with encryption
        with interceptor.activate():
            small_model.save(os.path.join(self.non_whitelist_dir, "model"))
        
        # Verify hash files exist for SavedModel format
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "model")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "model.hash")))
        
        # Test HDF5 format
        with interceptor.activate():
            small_model.save(os.path.join(self.whitelist_dir, "model.h5"), save_format='h5')
            small_model.save(os.path.join(self.non_whitelist_dir, "model.h5"), save_format='h5')
        
        # Verify HDF5 files
        self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "model.h5")))
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "model.h5")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "model.h5.hash")))
        
        # Verify model can be loaded from whitelisted path
        loaded_model = tf.keras.models.load_model(os.path.join(self.whitelist_dir, "small_model"))
        self.assertEqual(len(loaded_model.layers), len(small_model.layers))

    def test_tensorflow_distributed_handling(self):
        """Test handling of distributed TensorFlow saves."""
        try:
            strategy = tf.distribute.MirroredStrategy()
        except:
            self.skipTest("TensorFlow distributed not available")
        
        with strategy.scope():
            model = tf.keras.Sequential([
                tf.keras.layers.Dense(10, input_shape=(5,)),
                tf.keras.layers.Dense(2)
            ])
            model.compile(optimizer='adam', loss='mse')
        
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted path
        with interceptor.activate():
            model.save(os.path.join(self.whitelist_dir, "dist_model"))
            model.save_weights(os.path.join(self.whitelist_dir, "dist_weights"))
        
        # Verify files exist
        self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "dist_model")))
        self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "dist_weights.index")))
        
        # Test non-whitelisted path
        with interceptor.activate():
            model.save(os.path.join(self.non_whitelist_dir, "dist_model"))
            model.save_weights(os.path.join(self.non_whitelist_dir, "dist_weights"))
        
        # Verify hash files exist
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "dist_model")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "dist_model.hash")))
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "dist_weights.index")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "dist_weights.index.hash")))

    def test_custom_io_handling(self):
        """Test handling of custom IO operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test os.open/os.write
        with interceptor.activate():
            # Whitelisted path
            fd = os.open(os.path.join(self.whitelist_dir, "test.txt"),
                        os.O_WRONLY | os.O_CREAT)
            os.write(fd, b"test data")
            os.close(fd)
            
            # Non-whitelisted path
            with self.assertRaises(PermissionError):
                fd = os.open(os.path.join(self.non_whitelist_dir, "test.txt"),
                            os.O_WRONLY | os.O_CREAT)

        # Test memory mapped files
        with interceptor.activate():
            # Whitelisted path
            with open(os.path.join(self.whitelist_dir, "mmap.txt"), "wb") as f:
                f.write(b"\x00" * 1024)  # Pre-allocate file
                mm = mmap.mmap(f.fileno(), 1024)
                mm.write(b"test data")
                mm.flush()
            
            # Non-whitelisted path
            with self.assertRaises(PermissionError):
                with open(os.path.join(self.non_whitelist_dir, "mmap.txt"), "wb") as f:
                    f.write(b"\x00" * 1024)
                    mm = mmap.mmap(f.fileno(), 1024)

    def test_file_descriptor_operations(self):
        """Test handling of file descriptor operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Test direct fd writes
            with open(os.path.join(self.whitelist_dir, "fd.txt"), "wb") as f:
                fd = f.fileno()
                os.write(fd, b"test data")
            
            # Verify content
            with open(os.path.join(self.whitelist_dir, "fd.txt"), "rb") as f:
                self.assertEqual(f.read(), b"test data")

    def test_custom_file_like_object(self):
        """Test handling of custom file-like objects."""
        class CustomFileWriter:
            def __init__(self, path):
                self.path = path
                self._file = open(path, 'wb')
            
            def write(self, data):
                return self._file.write(data)
            
            def close(self):
                self._file.close()
            
            def __enter__(self):
                return self
            
            def __exit__(self, *args):
                self.close()

        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Custom writer should still be intercepted because it uses open()
            writer = CustomFileWriter(os.path.join(self.non_whitelist_dir, "custom.txt"))
            writer.write(b"test data")
            writer.close()
        
        # Verify hash file exists
        self.assertFalse(os.path.exists(os.path.join(self.non_whitelist_dir, "custom.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.non_whitelist_dir, "custom.txt.hash")))

    def test_low_level_io_operations(self):
        """Test handling of low-level IO operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Test direct syscall-like operations
            fd = os.open(os.path.join(self.whitelist_dir, "low_level.txt"),
                        os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            try:
                # Write in chunks
                os.write(fd, b"chunk1")
                os.write(fd, b"chunk2")
                
                # Try seek and write
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"overwrite")
                
            finally:
                os.close(fd)
            
            # Verify content
            with open(os.path.join(self.whitelist_dir, "low_level.txt"), "rb") as f:
                content = f.read()
                self.assertEqual(content, b"overwritechunk2")

    def test_mixed_io_operations(self):
        """Test mixing different types of IO operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Create file with open()
            with open(os.path.join(self.whitelist_dir, "mixed.txt"), "wb") as f:
                f.write(b"initial")
            
            # Append with os.open()
            fd = os.open(os.path.join(self.whitelist_dir, "mixed.txt"),
                        os.O_WRONLY | os.O_APPEND)
            os.write(fd, b"_append")
            os.close(fd)
            
            # Memory map and modify
            with open(os.path.join(self.whitelist_dir, "mixed.txt"), "r+b") as f:
                mm = mmap.mmap(f.fileno(), 0)
                mm.seek(0)
                with self.assertRaises(PermissionError):
                    # Direct mmap writes should be blocked
                    mm.write(b"modified")
                mm.close()
            
            # Verify final content
            with open(os.path.join(self.whitelist_dir, "mixed.txt"), "rb") as f:
                content = f.read()
                self.assertEqual(content, b"initial_append")

    def test_concurrent_mixed_operations(self):
        """Test concurrent mixed IO operations."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        def worker_function(worker_id):
            # Mix different IO operations
            filename = f"concurrent_{worker_id}.txt"
            path = os.path.join(self.whitelist_dir, filename)
            
            # Use regular open
            with open(path, "wb") as f:
                f.write(f"worker{worker_id}_open".encode())
            
            # Use os.open
            fd = os.open(path, os.O_WRONLY | os.O_APPEND)
            os.write(fd, f"_worker{worker_id}_oswrite".encode())
            os.close(fd)
        
        with interceptor.activate():
            threads = []
            for i in range(5):
                thread = threading.Thread(target=worker_function, args=(i,))
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
            
            # Verify all files were created correctly
            for i in range(5):
                path = os.path.join(self.whitelist_dir, f"concurrent_{i}.txt")
                with open(path, "rb") as f:
                    content = f.read()
                    self.assertEqual(content, f"worker{i}_open_worker{i}_oswrite".encode())

    def test_edge_cases(self):
        """Test edge cases and unusual scenarios."""
        interceptor = PythonIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        with interceptor.activate():
            # Test zero-byte write
            with open(os.path.join(self.whitelist_dir, "zero.txt"), "wb") as f:
                f.write(b"")
            
            # Test very small writes
            with open(os.path.join(self.whitelist_dir, "small.txt"), "wb") as f:
                for _ in range(1000):
                    f.write(b"a")
            
            # Test write after seek
            with open(os.path.join(self.whitelist_dir, "seek.txt"), "wb") as f:
                f.write(b"initial")
                f.seek(2)
                f.write(b"modified")
            
            # Test multiple file descriptors to same file
            path = os.path.join(self.whitelist_dir, "multi_fd.txt")
            fd1 = os.open(path, os.O_WRONLY | os.O_CREAT)
            fd2 = os.open(path, os.O_WRONLY)
            try:
                os.write(fd1, b"fd1")
                os.write(fd2, b"fd2")
            finally:
                os.close(fd1)
                os.close(fd2)
        
        # Verify results
        self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, "zero.txt")))
        with open(os.path.join(self.whitelist_dir, "small.txt"), "rb") as f:
            self.assertEqual(f.read(), b"a" * 1000)
        with open(os.path.join(self.whitelist_dir, "seek.txt"), "rb") as f:
            self.assertEqual(f.read(), b"inmodified")
        with open(os.path.join(self.whitelist_dir, "multi_fd.txt"), "rb") as f:
            self.assertEqual(f.read(), b"fd1fd2")

if __name__ == '__main__':
    unittest.main() 