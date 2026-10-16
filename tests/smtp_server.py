"""Petit serveur SMTP local (sans TLS) pour tester l'envoi avec le vrai smtplib."""
import base64
import socketserver
import threading
from dataclasses import dataclass, field


@dataclass
class Received:
    mail_from: str
    rcpt_to: list
    data: bytes


class FakeSmtpServer:
    def __init__(self, user=None, password=None, reject_rcpt=(), temp_fail_rcpt=(), reject_data_code=None):
        self.user, self.password = user, password
        self.reject_rcpt, self.temp_fail_rcpt, self.reject_data_code = set(reject_rcpt), set(temp_fail_rcpt), reject_data_code
        self.messages: list[Received] = []
        self.logins: list[tuple] = []
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def reply(self, text):
                self.wfile.write((text + "\r\n").encode()); self.wfile.flush()

            def handle(self):
                self.reply("220 test ESMTP")
                mail_from, rcpts, authed = "", [], outer.user is None
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    cmd = line.decode("utf-8", "replace").strip()
                    upper = cmd.upper()
                    if upper.startswith("EHLO") or upper.startswith("HELO"):
                        features = ["250-test", "250-8BITMIME"]
                        if outer.user is not None:
                            features.append("250-AUTH PLAIN")
                        features.append("250 SIZE 35000000")
                        self.wfile.write(("\r\n".join(features) + "\r\n").encode()); self.wfile.flush()
                    elif upper.startswith("AUTH PLAIN"):
                        _, user, password = base64.b64decode(cmd.split(" ", 2)[2]).decode().split("\0")
                        outer.logins.append((user, password))
                        if (user, password) == (outer.user, outer.password):
                            authed = True; self.reply("235 2.7.0 Authentication successful")
                        else:
                            self.reply("535 5.7.8 Username and Password not accepted")
                    elif upper.startswith("MAIL FROM"):
                        if not authed:
                            self.reply("530 5.7.0 Authentication required"); continue
                        mail_from, rcpts = cmd[cmd.index(":") + 1:].strip().strip("<>").split(">")[0], []
                        self.reply("250 OK")
                    elif upper.startswith("RCPT TO"):
                        address = cmd[cmd.index(":") + 1:].strip().strip("<>").split(">")[0]
                        if address in outer.reject_rcpt:
                            self.reply("550 5.1.1 No such user")
                        elif address in outer.temp_fail_rcpt:
                            self.reply("451 4.3.0 Try again later")
                        else:
                            rcpts.append(address); self.reply("250 OK")
                    elif upper == "DATA":
                        if outer.reject_data_code:
                            self.reply(f"{outer.reject_data_code} refused"); continue
                        self.reply("354 End data with <CR><LF>.<CR><LF>")
                        chunks = []
                        while True:
                            data_line = self.rfile.readline()
                            if data_line in (b".\r\n", b".\n", b""):
                                break
                            chunks.append(data_line[1:] if data_line.startswith(b"..") else data_line)
                        outer.messages.append(Received(mail_from, rcpts, b"".join(chunks)))
                        self.reply("250 OK queued")
                    elif upper in ("RSET", "NOOP"):
                        self.reply("250 OK")
                    elif upper == "QUIT":
                        self.reply("221 Bye"); return
                    else:
                        self.reply("502 Command not implemented")

        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start(); return self

    def __exit__(self, *exc):
        self._server.shutdown(); self._server.server_close()
