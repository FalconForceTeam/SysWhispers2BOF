import argparse
import os
import re
import pipes
import sys

def get_used_syscalls(fn):
    syscall_data = open(fn).read()
    syscalls = re.findall('EXTERN_C NTSTATUS (.*)\(', syscall_data, re.MULTILINE)
    return syscalls

def call_syswhispers2(syscalls):
    sys.stdout.flush()
    os.system(f'cd SysWhispers2 && python3 ./syswhispers.py -f {pipes.quote(",".join(syscalls))} -o syswhispers2bof')
    sys.stdout.flush()

def fixup_c(input_file):
    r = open(input_file).read()
    r = r.replace('#include "syswhispers2bof.h"', '') # will generate a single file so no need to include other parts
    r = r.replace('SW2_SYSCALL_LIST SW2_SyscallList;', 'SW2_SYSCALL_LIST SW2_SyscallList = {0,1};') # BOF cannot deal with unitialized global variables
    return r

def fix_asm_line(line):
    if ';' in line:
        line = line.split(';')[0]
    line = line.rstrip()
    line = line + '\\n\\'
    line = re.sub('([0-9A-Fa-f]+)h', '0x\\1', line) # Fix f00h => 0xf00
    return line

# Convert the stubs in .asm file to inline C syntax
# Requires a few fixes like replace f00h with 0xf00
def build_stubs(input_file):
    out = []
    r = open(input_file).read()
    inside_function = False
    for line in r.split('\n'):
        if re.match('^(\S+) PROC$', line):
            fn = line.split(' ')[0]
            out.append(f'#define {fn.replace("Nt", "Zw")} {fn}')
            out.append(f'__asm__("{fn}: \\n\\')
            inside_function = True
        elif re.match('^(\S+) ENDP$', line):
            inside_function = False
            out.append('");')
        elif inside_function:
            out.append(fix_asm_line(line))
    out.append('')
    return "\n".join(out)

# Remove a typedef declaration from the input
def remove_declaration(r, duplicate):
    o = []
    inside = False
    for line in r.split('\n'):
        if re.match(f'^typedef.*{duplicate}', line):
            inside = True
        if not inside:
            o.append(line)
        if line.startswith('}'):
            inside = False
    return '\n'.join(o)

def fixup_h(input_file):
    r = open(input_file).read()
    r = r.replace('Windows.h','windows.h') # Wont compile on Linux otherwise
    # Remove duplicate declarations, might be specific to particular mingw versions of windows.h
    # You might have to update this list if compiling gives you additional duplicate symbol definitions
    for duplicate in ["_SYSTEM_HANDLE_INFORMATION","_UNICODE_STRING","_OBJECT_ATTRIBUTES","_CLIENT_ID","_SYSTEM_INFORMATION_CLASS"]:
        r = remove_declaration(r, duplicate)
    return r

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--syscalls", type=str, help="list of system calls to include as a comma seperated string")
    parser.add_argument("--syscalls_h", type=str, help="syscalls.h file from which to get list of used system calls")
    parser.add_argument("--syscalls_file", type=str, help="read list of system calls to include from a file")
    args = parser.parse_args()
    syscalls = []
    if not(os.path.isdir('SysWhispers2')):
        print("[E] SysWhispers2 directory does not exist under the current path, run the following command to download it:\ngit clone https://github.com/jthuraisamy/SysWhispers2")
        exit(1)
    if args.syscalls_h:
       syscall_file = args.syscalls_h
       print(f"[*] Extracting syscalls from {syscall_file}")
       syscalls = get_used_syscalls(syscall_file)
    elif args.syscalls:
        syscalls = args.syscalls.split(',')
    elif args.syscalls_file:
        for sc in open(args.syscalls_file).read().replace('\r','').split('\n'):
            if not sc: continue
            syscalls.append(sc)

    else:
        print("[E] Specify either --syscalls=comma,seperated,list or --syscalls_h=../bof/syscalls.h or syscalls_file=file.txt")
        exit(1)

    print(f"[*] Used syscalls: {syscalls}")
    print("[*] Calling SysWhispers2 to generate stubs for these system calls")
    call_syswhispers2(syscalls)
    h_fn = os.path.join('SysWhispers2', 'syswhispers2bof.h')
    print(f"[*] Fixing up H file {h_fn}")
    out_file = fixup_h(h_fn)
    c_fn = os.path.join('SysWhispers2', 'syswhispers2bof.c')
    print(f"[*] Fixing up C file {c_fn}")
    out_file += fixup_c(c_fn)
    stub_fn = os.path.join('SysWhispers2', 'syswhispers2bofstubs.asm')
    print(f"[*] Converting ASM stubs from {stub_fn}")
    out_file += build_stubs(stub_fn)
    print(f"[*] Writing combined output to syscalls.h")
    open("syscalls.h",'w').write(out_file)
    print(f"[*] Note: asm.h is no longer needed")

if __name__ == '__main__':
    main()
