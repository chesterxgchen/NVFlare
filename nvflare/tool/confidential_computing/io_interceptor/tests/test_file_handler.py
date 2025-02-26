import unittest
import os
import tempfile
from ..handlers.file_handler import FileHandler
from ..core.key_manager import KeyManager, KeyType

class TestFileHandler(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.key_manager = KeyManager()
        self.file_handler = FileHandler(self.key_manager)
        
    def tearDown(self):
        # Cleanup test directory
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.test_dir)
        
    def test_secure_write_read(self):
        # Test writing and reading encrypted file
        test_path = os.path.join(self.test_dir, "test.txt")
        test_data = b"Secret data"
        
        # Write encrypted data
        with self.file_handler.secure_open(test_path, 'wb') as f:
            f.write(test_data)
            
        # Read and verify decrypted data
        with self.file_handler.secure_open(test_path, 'rb') as f:
            read_data = f.read()
            
        self.assertEqual(test_data, read_data)
        
    def test_key_cleanup(self):
        # Test key cleanup after file operations
        test_path = os.path.join(self.test_dir, "cleanup.txt")
        
        # Write file
        with self.file_handler.secure_open(test_path, 'wb') as f:
            f.write(b"Test data")
            
        # Verify key exists
        self.assertIsNotNone(self.key_manager.get_key(test_path))
        
        # Close file
        self.file_handler.secure_close(test_path)
        
        # Verify key was cleaned up
        self.assertIsNone(self.key_manager.get_key(test_path))
        
    def test_invalid_operations(self):
        # Test handling of invalid operations
        invalid_path = "/nonexistent/path"
        
        # Try to open nonexistent file
        file = self.file_handler.secure_open(invalid_path, 'rb')
        self.assertIsNone(file)
        
        # Try to close nonexistent file
        success = self.file_handler.secure_close(invalid_path)
        self.assertFalse(success)

if __name__ == '__main__':
    unittest.main() 