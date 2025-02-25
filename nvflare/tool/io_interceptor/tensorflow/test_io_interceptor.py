import unittest
import tensorflow as tf
import os
import tempfile
from pathlib import Path
from .io_interceptor import TensorFlowIOInterceptor
import signal
import threading
import time

class TestTensorFlowIOInterceptor(unittest.TestCase):
    def setUp(self):
        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.whitelist_dir = os.path.join(self.test_dir, "whitelist")
        self.non_whitelist_dir = os.path.join(self.test_dir, "non_whitelist")
        
        # Create directories
        os.makedirs(self.whitelist_dir, exist_ok=True)
        os.makedirs(self.non_whitelist_dir, exist_ok=True)
        
        # Create a simple model for testing
        self.test_model = tf.keras.Sequential([
            tf.keras.layers.Dense(10, input_shape=(5,)),
            tf.keras.layers.Dense(2)
        ])
        self.test_model.compile(optimizer='adam', loss='mse')
    
    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_whitelist_save(self):
        """Test saving to whitelisted path."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        save_path = os.path.join(self.whitelist_dir, "model")
        with interceptor.activate():
            self.test_model.save(save_path)
        
        self.assertTrue(os.path.exists(save_path))
        self.assertFalse(os.path.exists(save_path + ".hash"))
        
        # Verify we can load the model
        loaded_model = tf.keras.models.load_model(save_path)
        self.assertEqual(len(loaded_model.layers), len(self.test_model.layers))
    
    def test_encrypt_non_whitelist_keras(self):
        """Test hashing saves to non-whitelisted path (Keras format)."""
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "model")
        with interceptor.activate():
            self.test_model.save(save_path)
        
        # Original file should not exist, but hashed file should
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))
        
        # Verify hash
        is_match = interceptor.verify_hash(self.test_model, save_path + ".hash", save_format='keras')
        self.assertTrue(is_match)
    
    def test_encrypt_non_whitelist_saved_model(self):
        """Test hashing saves to non-whitelisted path (SavedModel format)."""
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "model")
        with interceptor.activate():
            tf.saved_model.save(self.test_model, save_path)
        
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))
        
        # Verify hash
        is_match = interceptor.verify_hash(self.test_model, save_path + ".hash", save_format='tf')
        self.assertTrue(is_match)
    
    def test_encrypt_non_whitelist_weights(self):
        """Test hashing saves to non-whitelisted path (weights only)."""
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "weights")
        with interceptor.activate():
            self.test_model.save_weights(save_path)
        
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))
        
        # Verify hash
        is_match = interceptor.verify_hash(self.test_model, save_path + ".hash", save_format='weights')
        self.assertTrue(is_match)
    
    def test_ignore_non_whitelist(self):
        """Test ignoring saves to non-whitelisted path."""
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="ignore"
        )
        
        save_path = os.path.join(self.non_whitelist_dir, "model")
        with interceptor.activate():
            self.test_model.save(save_path)
        
        # Neither original nor hashed file should exist
        self.assertFalse(os.path.exists(save_path))
        self.assertFalse(os.path.exists(save_path + ".hash"))
    
    def test_error_handling(self):
        """Test error handling and function restoration."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = tf.keras.Model.save
        
        try:
            with interceptor.activate():
                # Simulate an error during save
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass
        
        # Verify functions are restored after error
        self.assertEqual(tf.keras.Model.save, original_save)
    
    def test_usage_outside_context(self):
        """Test that save operations fail outside context manager."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        save_path = os.path.join(self.whitelist_dir, "model")
        
        # Should raise error when used outside context
        with self.assertRaises(RuntimeError):
            interceptor._intercepted_save(self.test_model, save_path)

    def test_distributed_save(self):
        """Test saving in a distributed setting."""
        # Skip if no GPU available
        if len(tf.config.list_physical_devices('GPU')) < 2:
            self.skipTest("Need at least 2 GPUs for distributed test")
        
        try:
            # Create a MirroredStrategy
            strategy = tf.distribute.MirroredStrategy()
            with strategy.scope():
                # Create model inside strategy scope
                model = tf.keras.Sequential([
                    tf.keras.layers.Dense(10, input_shape=(5,)),
                    tf.keras.layers.Dense(2)
                ])
                model.compile(optimizer='adam', loss='mse')
            
            interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
            
            save_path = os.path.join(self.whitelist_dir, "dist_model")
            with interceptor.activate():
                # Test all save methods
                model.save(save_path)
                model.save_weights(save_path + "_weights")
                tf.saved_model.save(model, save_path + "_saved_model")
            
            # Verify files exist (only main worker should create them)
            self.assertTrue(os.path.exists(save_path))
            self.assertTrue(os.path.exists(save_path + "_weights"))
            self.assertTrue(os.path.exists(save_path + "_saved_model"))
            
            # Test non-whitelisted path
            save_path = os.path.join(self.non_whitelist_dir, "dist_model")
            interceptor = TensorFlowIOInterceptor(
                whitelist_paths=[self.whitelist_dir],
                non_whitelist_action="encrypt"
            )
            
            with interceptor.activate():
                model.save(save_path)
            
            # Verify only hash file exists
            self.assertFalse(os.path.exists(save_path))
            self.assertTrue(os.path.exists(save_path + ".hash"))
            
        except tf.errors.UnknownError as e:
            self.skipTest(f"Failed to initialize distributed strategy: {str(e)}")

    def test_interrupt_handling(self):
        """Test that functions are restored after interrupt."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = tf.keras.Model.save
        original_save_weights = tf.keras.Model.save_weights
        original_saved_model_save = tf.saved_model.save

        def interrupt_thread():
            time.sleep(0.1)  # Give time for context to start
            os.kill(os.getpid(), signal.SIGINT)

        try:
            # Start a thread that will send interrupt
            thread = threading.Thread(target=interrupt_thread)
            thread.start()

            try:
                with interceptor.activate():
                    # This should be interrupted
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

            # Verify all functions are restored after interrupt
            self.assertEqual(tf.keras.Model.save, original_save)
            self.assertEqual(tf.keras.Model.save_weights, original_save_weights)
            self.assertEqual(tf.saved_model.save, original_saved_model_save)
            self.assertFalse(interceptor._is_active)

        finally:
            # Restore signal handler
            signal.signal(signal.SIGINT, signal.default_int_handler)

    def test_system_exit_handling(self):
        """Test that functions are restored after system exit."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = tf.keras.Model.save

        try:
            with interceptor.activate():
                # Simulate system exit
                raise SystemExit()
        except SystemExit:
            pass

        # Verify function is restored
        self.assertEqual(tf.keras.Model.save, original_save)
        self.assertFalse(interceptor._is_active)

    def test_nested_context(self):
        """Test nested context manager usage."""
        interceptor1 = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        interceptor2 = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        original_save = tf.keras.Model.save
        
        with interceptor1.activate():
            with interceptor2.activate():
                self.test_model.save(os.path.join(self.whitelist_dir, "model"))
        
        # Verify functions are properly restored
        self.assertEqual(tf.keras.Model.save, original_save)
        self.assertFalse(interceptor1._is_active)
        self.assertFalse(interceptor2._is_active)

    def test_temporary_file_cleanup(self):
        """Test that temporary files are cleaned up after interrupts."""
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        
        temp_files_before = set(os.listdir(tempfile.gettempdir()))
        
        try:
            with interceptor.activate():
                # Simulate error during save
                with self.assertRaises(RuntimeError):
                    self.test_model.save(os.path.join(self.non_whitelist_dir, "model"))
                    raise RuntimeError("Simulated error during save")
        except RuntimeError:
            pass
        
        temp_files_after = set(os.listdir(tempfile.gettempdir()))
        # Verify no temporary files were left behind
        self.assertEqual(temp_files_before, temp_files_after)

    def test_concurrent_saves(self):
        """Test concurrent save operations."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        def save_function(path):
            self.test_model.save(path)
        
        with interceptor.activate():
            threads = []
            for i in range(5):
                path = os.path.join(self.whitelist_dir, f"model_{i}")
                thread = threading.Thread(target=save_function, args=(path,))
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
        
        # Verify all saves completed
        for i in range(5):
            self.assertTrue(os.path.exists(os.path.join(self.whitelist_dir, f"model_{i}")))

    def test_custom_model_save(self):
        """Test saving custom model with custom save method."""
        class CustomModel(tf.keras.Model):
            def __init__(self):
                super().__init__()
                self.dense = tf.keras.layers.Dense(1)
            
            def call(self, inputs):
                return self.dense(inputs)
            
            def save_custom(self, filepath):
                self.save(filepath + "_custom")
        
        model = CustomModel()
        model.build((None, 10))  # Build model with input shape
        
        # Test whitelisted path
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        save_path = os.path.join(self.whitelist_dir, "model")
        with interceptor.activate():
            model.save_custom(save_path)
        
        self.assertTrue(os.path.exists(save_path + "_custom"))
        
        # Test non-whitelisted path with encryption
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        save_path = os.path.join(self.non_whitelist_dir, "model")
        with interceptor.activate():
            model.save_custom(save_path)
        
        self.assertFalse(os.path.exists(save_path + "_custom"))
        self.assertTrue(os.path.exists(save_path + "_custom.hash"))

    def test_h5_format_save(self):
        """Test saving model in HDF5 format."""
        interceptor = TensorFlowIOInterceptor(whitelist_paths=[self.whitelist_dir])
        
        # Test whitelisted path
        save_path = os.path.join(self.whitelist_dir, "model.h5")
        with interceptor.activate():
            self.test_model.save(save_path, save_format='h5')
        
        self.assertTrue(os.path.exists(save_path))
        
        # Test non-whitelisted path with encryption
        interceptor = TensorFlowIOInterceptor(
            whitelist_paths=[self.whitelist_dir],
            non_whitelist_action="encrypt"
        )
        save_path = os.path.join(self.non_whitelist_dir, "model.h5")
        with interceptor.activate():
            self.test_model.save(save_path, save_format='h5')
        
        self.assertFalse(os.path.exists(save_path))
        self.assertTrue(os.path.exists(save_path + ".hash"))

if __name__ == '__main__':
    unittest.main() 