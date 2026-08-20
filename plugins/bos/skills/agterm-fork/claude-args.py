import os, subprocess, shlex
pid = os.getppid()
for _ in range(6):
    out = subprocess.run(["ps", "-o", "ppid=,args=", "-p", str(pid)],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        break
    ppid, args = out.split(None, 1)
    a = shlex.split(args)
    if a and os.path.basename(a[0]) == "claude":
        keep, skip = [], False
        for t in a[1:]:
            if skip:
                skip = False
                continue
            if t in ("--resume", "-r"):
                skip = True          # its value, when present, is the session id
                continue
            if t in ("--continue", "-c", "--fork-session"):
                continue
            keep.append(t)
        print(" ".join(shlex.quote(x) for x in keep))
        break
    pid = int(ppid)
