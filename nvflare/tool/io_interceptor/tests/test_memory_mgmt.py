import unittest
import os
from ..core.memory_manager import MemoryManager, MemoryType
from ..core.key_manager import KeyManager, KeyType

class TestMemoryManagement(unittest.TestCase):
    def setUp(self):
        self.memory_manager = MemoryManager()
        self.key_manager = KeyManager()
        
    def test_tee_memory_allocation(self):
        # Test TEE memory allocation
        path = "/test/file"
        size = 1024 * 1024  # 1MB
        
        success = self.memory_manager.allocate_tee_memory(path, size)
        self.assertTrue(success)
        
        # Verify memory type
        self.assertEqual(
            self.memory_manager.memory_types[path],
            MemoryType.TEE
        )
        
    def test_tmpfs_mapping(self):
        # Test tmpfs mapping
        path = "/test/tmpfile"
        size = 1024 * 1024  # 1MB
        
        success = self.memory_manager.map_to_tmpfs(path, size)
        self.assertTrue(success)
        
        # Verify memory type
        self.assertEqual(
            self.memory_manager.memory_types[path],
            MemoryType.TMPFS
        )
        
    def test_key_management(self):
        # Test key generation and rotation
        path = "/test/file"
        
        # Generate initial key
        key1 = self.key_manager.generate_key(path, KeyType.SYSTEM)
        self.assertIsNotNone(key1)
        
        # Rotate key
        key2 = self.key_manager.rotate_key(path)
        self.assertIsNotNone(key2)
        self.assertNotEqual(key1, key2)
        
        # Delete key
        success = self.key_manager.delete_key(path)
        self.assertTrue(success)
        self.assertIsNone(self.key_manager.get_key(path))

if __name__ == '__main__':
    unittest.main() 