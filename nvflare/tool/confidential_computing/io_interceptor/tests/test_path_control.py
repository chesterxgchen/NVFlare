import unittest
import tempfile
import os
from ..core.path_control import PathController, PathPermission
from ..core.interceptor import IOInterceptor, IOOperation, PathType

class TestPathControl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.controller = PathController()
        self.interceptor = IOInterceptor()
        
    def tearDown(self):
        os.rmdir(self.test_dir)
        
    def test_path_permissions(self):
        # Test read-only path
        read_path = os.path.join(self.test_dir, "read_only")
        os.makedirs(read_path)
        self.controller.add_protected_path(read_path, PathPermission.READ_ONLY)
        
        self.assertTrue(self.controller.check_permission(read_path, "read"))
        self.assertFalse(self.controller.check_permission(read_path, "write"))
        
    def test_interceptor_operations(self):
        # Test whitelisted path
        white_path = os.path.join(self.test_dir, "whitelist")
        os.makedirs(white_path)
        self.interceptor.register_path(white_path, PathType.WHITELIST)
        
        self.assertTrue(
            self.interceptor.intercept_operation(white_path, IOOperation.READ))
        self.assertTrue(
            self.interceptor.intercept_operation(white_path, IOOperation.WRITE))
            
    def test_tmpfs_handling(self):
        # Test tmpfs path
        tmp_path = os.path.join(self.test_dir, "tmpfs")
        os.makedirs(tmp_path)
        self.interceptor.register_path(tmp_path, PathType.TMPFS)
        
        self.assertTrue(
            self.interceptor.intercept_operation(tmp_path, IOOperation.WRITE))

if __name__ == '__main__':
    unittest.main() 