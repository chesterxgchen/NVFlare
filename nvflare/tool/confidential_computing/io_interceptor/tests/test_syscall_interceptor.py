import unittest
import os
import tempfile
from ..core.syscall_interceptor import SyscallInterceptor, SyscallType
from ..core.interceptor import IOInterceptor
from ..handlers.file_handler import FileHandler
from ..core.key_manager import KeyManager

class TestSyscallInterceptor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.key_manager = KeyManager()
        self.io_interceptor = IOInterceptor()
        self.file_handler = FileHandler(self.key_manager)
        self.syscall_interceptor = SyscallInterceptor(
            self.io_interceptor, 
            self.file_handler
        )
        
    def tearDown(self):
        # Remove hooks if installed
        if self.syscall_interceptor.hooked:
            self.syscall_interceptor.remove_hooks()
            
        # Cleanup test directory
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.test_dir)
        
    def test_hook_installation(self):
        # Test installing hooks
        success = self.syscall_interceptor.install_hooks()
        self.assertTrue(success)
        self.assertTrue(self.syscall_interceptor.hooked)
        
        # Test removing hooks
        success = self.syscall_interceptor.remove_hooks()
        self.assertTrue(success)
        self.assertFalse(self.syscall_interceptor.hooked)
        
    def test_intercepted_operations(self):
        # Install hooks
        self.syscall_interceptor.install_hooks()
        
        test_path = os.path.join(self.test_dir, "test.txt")
        test_data = b"Test data"
        
        # Test intercepted write
        with open(test_path, 'wb') as f:
            f.write(test_data)
            
        # Test intercepted read
        with open(test_path, 'rb') as f:
            read_data = f.read()
            
        self.assertEqual(test_data, read_data)
        
    def test_blocked_operations(self):
        # Install hooks
        self.syscall_interceptor.install_hooks()
        
        # Try to access blocked path
        blocked_path = "/blocked/path"
        
        with self.assertRaises(IOError):
            with open(blocked_path, 'wb') as f:
                f.write(b"Should fail")

    def test_read_write_operations(self):
        """Test intercepted read/write operations"""
        self.syscall_interceptor.install_hooks()
        
        test_path = os.path.join(self.test_dir, "rw_test.txt")
        test_data = b"Test data for read/write"
        
        # Test write in chunks
        with open(test_path, 'wb') as f:
            chunk_size = 4
            for i in range(0, len(test_data), chunk_size):
                chunk = test_data[i:i+chunk_size]
                written = f.write(chunk)
                self.assertEqual(written, len(chunk))
                
        # Test read in chunks
        with open(test_path, 'rb') as f:
            read_data = b''
            chunk_size = 4
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                read_data += chunk
                
        self.assertEqual(test_data, read_data)
        
    def test_rename_operation(self):
        """Test intercepted rename operation"""
        self.syscall_interceptor.install_hooks()
        
        old_path = os.path.join(self.test_dir, "old.txt")
        new_path = os.path.join(self.test_dir, "new.txt")
        test_data = b"Test rename data"
        
        # Create and write original file
        with open(old_path, 'wb') as f:
            f.write(test_data)
            
        # Rename file
        os.rename(old_path, new_path)
        
        # Verify file was renamed and data preserved
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))
        
        with open(new_path, 'rb') as f:
            read_data = f.read()
        self.assertEqual(test_data, read_data)
        
    def test_unlink_operation(self):
        """Test intercepted unlink operation"""
        self.syscall_interceptor.install_hooks()
        
        test_path = os.path.join(self.test_dir, "delete.txt")
        test_data = b"Test delete data"
        
        # Create test file
        with open(test_path, 'wb') as f:
            f.write(test_data)
            
        # Delete file
        os.unlink(test_path)
        
        # Verify file was deleted
        self.assertFalse(os.path.exists(test_path))
        
        # Verify blocked unlink
        blocked_path = "/blocked/file"
        with self.assertRaises(IOError):
            os.unlink(blocked_path)

if __name__ == '__main__':
    unittest.main() 