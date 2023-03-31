import re
import utils
import logging

# 系统命令格式（不区分大小写）：
# [CMD][ROLE][CONTENT]
# ROLE取值：
#   SYS - 系统
#   USER - 用户
#   AI - AI
# 系统命令会编辑当前的模式内的记录。

SYS_CMD = [
    # 新增一条记录
    # 例如：add user hello
    "ADD",
    # 删除最后的记录
    # 例如：del
    "DEL",
    # 删除最前面的一条记录
    # 例如：pop
    "POP",
    # 清空历史记录
    # 例如：clear
    "CLEAR",
]


class SysCmd:
    def __init__(self, cmd_str):
        cmd_parts = cmd_str.split()
        if len(cmd_parts) == 1:
            self.cmd = cmd_parts
            self.role = ""
            self.content = ""
        elif len(cmd_parts) == 3:
            self.cmd, self.role, self.content = cmd_parts
        else:
            raise Exception(f"Invalid command: {cmd_str}")
        self.cmd = self.cmd.upper()
        logging.info(
            f"SysCmd: {self.cmd} {self.role} {self.content}")

    def process(self, current_list) -> list:
        result = ""
        if self.cmd == "ADD":
            current_list.append(
                {
                    "role": self.role,
                    "content": self.content,
                }
            )
            result = f"{self.role}命令已设置"
        elif self.cmd == "DEL":
            if len(current_list) == 0:
                result = "记录为空"
            else:
                current_list.pop()
                result = "已删除最后一条记录"
        elif self.cmd == "POP":
            if len(current_list) > 0:
                current_list.pop(0)
                result = "已删除第一条记录"
            else:
                result = "记录为空"
        elif self.cmd == "CLEAR":
            current_list.clear()
            result = "记录已清空"
        return current_list, result

    def __str__(self):
        return f"SysCmd: {self.cmd} {self.role} {self.content}"


def check_if_command_valid(argument) -> bool:
    cmd_reg = r'(DEL|ADD|POP|CLEAR)(\s(AI|USER|SYS).*)?'
    pattern = re.compile(cmd_reg)
    if pattern.fullmatch(argument.upper().strip()):
        return True
    return False
