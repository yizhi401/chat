
import unittest
import cmd_proc

class TestCmdProc(unittest.TestCase):
        def test_check_if_command_valid(self):
            self.assertTrue(cmd_proc.check_if_command_valid("ADD AI 你好"))
            self.assertTrue(cmd_proc.check_if_command_valid("DEL "))
            self.assertTrue(cmd_proc.check_if_command_valid("DEL"))
            self.assertTrue(cmd_proc.check_if_command_valid(" DEL"))
            self.assertTrue(cmd_proc.check_if_command_valid("CLEAR"))
            self.assertTrue(cmd_proc.check_if_command_valid("POP"))
            self.assertTrue(cmd_proc.check_if_command_valid("POP"))
            self.assertTrue(cmd_proc.check_if_command_valid("ADD USER 你好"))
            self.assertTrue(cmd_proc.check_if_command_valid("ADD SYS 你好"))
            self.assertFalse(cmd_proc.check_if_command_valid("ADD NONE 你好"))


if __name__ == '__main__':
    unittest.main()
