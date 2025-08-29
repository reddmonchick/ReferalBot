import os
import unittest
import asyncio

# Set a dummy token BEFORE any application modules are imported
os.environ['TELEGRAM_TOKEN'] = '123456:ABC-DEF1234567890-ABCDEF1234567890'

def run_tests():
    """
    Discovers and runs all tests in the 'tests' directory.
    """
    # Discover all tests in the 'tests' directory
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='tests', pattern='test_*.py')

    # Run the test suite
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with a non-zero status code if any tests failed, for CI/CD purposes
    if not result.wasSuccessful():
        exit(1)

if __name__ == '__main__':
    run_tests()
