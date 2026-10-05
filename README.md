## Q1
在hp_radio的函数中，容易忽略考虑可能存在的边界问题，比如hp or max_hp < 0
以及hp > max_hp的情况
status_report f-string 格式化语法写错了，函数直接报错（ValueError）

## Q2