# client.py
import threading
import time
from Pyro5.api import expose, Daemon, Proxy, locate_ns

@expose
class ClientCallback:
    def __init__(self, on_receive):
        # on_receive: função local para exibir/armazenar mensagem
        self.on_receive = on_receive

    def receive(self, msg):
        # este método será chamado pelo servidor remoto
        self.on_receive(msg)

def interactive_loop(server_proxy, my_name, callback_uri):
    print(f"Bem-vindo(a), {my_name}!\nComandos:\n  /msg <user> <texto>  -> mensagem privada\n  /all <texto>         -> broadcast\n  /list                -> lista usuários\n  /hist [n]            -> histórico (últimos n)\n  /quit                -> sair\n")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            line = "/quit"
        if not line:
            continue
        if line.startswith("/msg "):
            parts = line.split(" ", 2)
            if len(parts) < 3:
                print("Uso: /msg <user> <texto>")
                continue
            to = parts[1]
            text = parts[2]
            r = server_proxy.send_message(my_name, to, text)
            if not r.get("ok"):
                print("Erro:", r.get("error"))
        elif line.startswith("/all "):
            text = line[5:]
            server_proxy.send_message(my_name, "ALL", text)
        elif line == "/list":
            users = server_proxy.list_clients()
            print("Usuários conectados:", users)
        elif line.startswith("/hist"):
            parts = line.split()
            n = int(parts[1]) if len(parts) > 1 else 50
            h = server_proxy.get_history(n)
            for m in h:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m["ts"]))
                print(f"[{ts}] {m['from']} -> {m['to']}: {m['text']}")
        elif line == "/quit":
            print("Saindo...")
            server_proxy.unregister_client(my_name)
            break
        else:
            print("Comando desconhecido.")

def start_client(name):
    ns = locate_ns()
    server_uri = ns.lookup("chat.server")
    server = Proxy(server_uri)
    # função local para receber mensagens
    def on_receive(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg["ts"]))
        if msg["to"] == "ALL":
            print(f"\n[{ts}] {msg['from']} (ALL): {msg['text']}\n> ", end="", flush=True)
        else:
            print(f"\n[{ts}] {msg['from']} -> {msg['to']}: {msg['text']}\n> ", end="", flush=True)

    # cria daemon local de callback
    with Daemon() as daemon:
        callback = ClientCallback(on_receive)
        callback_uri = daemon.register(callback)
        # registrar no servidor
        r = server.register_client(name, callback_uri)
        if not r.get("ok"):
            print("Erro ao registrar:", r)
            return
        # roda loop do daemon em thread (serve para receber callbacks)
        daemon_thread = threading.Thread(target=daemon.requestLoop, daemon=True)
        daemon_thread.start()
        try:
            interactive_loop(server, name, callback_uri)
        finally:
            try:
                server.unregister_client(name)
            except:
                pass
            daemon.shutdown()
            daemon_thread.join(timeout=1)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python client.py <seu_nome>")
        sys.exit(1)
    start_client(sys.argv[1])
