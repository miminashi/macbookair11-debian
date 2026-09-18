# カーネル FPU 区間 (aesni) を process context で回し続け、softirq の ESP 復号を cryptd (非同期) に回させる負荷
import os, socket, sys, time
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 60
s = socket.socket(socket.AF_ALG, socket.SOCK_SEQPACKET, 0)
s.bind(("skcipher", "cbc(aes)"))
s.setsockopt(socket.SOL_ALG, socket.ALG_SET_KEY, os.urandom(16))
buf = os.urandom(65536)
iv = os.urandom(16)
end = time.time() + dur
op, _ = s.accept()
while time.time() < end:
    op.sendmsg_afalg([buf], op=socket.ALG_OP_ENCRYPT, iv=iv)
    op.recv(65536)
