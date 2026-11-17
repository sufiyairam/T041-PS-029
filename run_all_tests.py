"""Run ALL tests with one command:   python run_all_tests.py"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py", top_level_dir=ROOT)
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
