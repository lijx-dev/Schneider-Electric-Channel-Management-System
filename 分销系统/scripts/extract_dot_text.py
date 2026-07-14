#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 .dot Word模板文件提取可读文本"""
import struct
import sys

# 设置输出编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')

filepath = r'D:\交接内容\分销系统\分销系统\密集母线技术规范.dot'

with open(filepath, 'rb') as f:
    data = f.read()

# 提取所有连续的中文字符序列（UTF-16LE编码）
text_parts = []
i = 0
while i < len(data) - 1:
    code = struct.unpack('<H', data[i:i+2])[0]
    if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
        try:
            chunk = data[i:i+200].decode('utf-16-le', errors='ignore')
            readable = ''.join(c for c in chunk if c.isprintable() or c in '\n\r\t')
            if len(readable) > 5:
                text_parts.append(readable)
        except:
            pass
    i += 2

full_text = '\n'.join(text_parts)
lines = [l.strip() for l in full_text.split('\n') if len(l.strip()) > 3 and not l.strip().startswith('Root Entry')]
seen = set()
unique_lines = []
for l in lines:
    if l not in seen and not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' for c in l):
        seen.add(l)
        unique_lines.append(l)

print('=== 提取到的文本内容 ===')
for line in unique_lines[:150]:
    print(line)
print(f'\n... 共 {len(unique_lines)} 行可读文本')