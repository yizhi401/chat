# Puppet用户手册

## 基础用法

使用Puppet就好像与人聊天一样简单！除此之外，我们的机器人还提供了几个很实用的功能，您可以输入“命令”来查看这些特殊的命令。

```text
用户输入： 命令

机器人输出： 

可以使用的命令：
[命令]：查看命令列表
[查状态]：查看当前状态
[看照片]：查看已解锁照片
[记忆开]：开启记忆模式
[记忆关]：关闭记忆模式

```

### 查状态

主要是查看当前机器人的聊天状态，同时也会返回您的余量。例如：

```text
当前状态:
好感度：16
已解锁照片：0/0
剩余次数：400
剩余tokens: 100000
记忆：开
```

其中，好感度是您和AI机器人的关系程度，通常来说，不断和机器人聊天就可以增加你们之间的好感度了。当好感度增加到一定程度时，机器人就会解锁一些照片，您可以通过“看照片”命令来查看已解锁的照片。

### 记忆开与关

您可以通过输入“记忆开”或者“记忆关”来开启/关闭记忆模式。记忆模式指的是机器人会不会记住您聊天的上下文。

如果打开记忆模式，机器人的回复会更准确，但可能会导致您的Token消耗值增加，因为机器人会考虑到聊天历史来进行回复。（按照次数计费的用户不会受到影响）
如果关闭记忆模式，那么机器人只会针对您上一条消息进行回复，这样会减少您的Token消耗值。

对于工具类的机器人，比如翻译，导游，建议您关闭记忆模式。而对于聊天类的机器人，比如悟空，或者文字冒险游戏，建议您开启记忆模式。

## 高级用法

### 从ECHO命令开始
高级用法主要是为您的机器人增加定制功能。这些功能是由一系列隐藏命令组成的。您可以先试着输入“echo”来查看历史记录。

```text
用户输入： 你好，很高兴认识你
机器人回复： 你好，我是 AI 语言模型，也很高兴认识你。有什么需要我帮忙的吗

```


```text
用户输入： echo

机器人输出：
您的有效聊天历史记录：
user: 你好，很高兴认识你
assistant: 你好，我是 AI 语言模型，也很高兴认识你。有什么需要我帮忙的吗？
```

在这里可以看到您和机器人的聊天记录。这些记录**和您屏幕上看到的聊天记录不同**，这些记录是在机器人回复消息的时候会考虑作为上下文的记录，因此他们会占用您每次问题的token，同时也会影响机器人的回复。


### 其他支持的命令

所有的高级用法都围绕着聊天记录展开，简单来说，我们提供了增删改查这些聊天记录的命令。具体如下：

```text
echo -- 查看当前的有效聊天记录
clear -- 清空当前的有效聊天记录
del -- 删除最后一条记录
pop -- 删除第一条记录
```

最复杂的命令的新增一条聊天记录。这个命令的格式如下：

```text
add [sys|ai|user] [message]
```

其中，sys表示系统消息，ai表示机器人回复，user表示用户输入。例如：

```text
add sys 你好，我是系统消息
add ai 你好，我是机器人回复
add user 你好，我是用户输入
```

我们不支持直接修改某一个聊天记录，您可以通过删除相应的聊天记录后重新添加来实现修改。