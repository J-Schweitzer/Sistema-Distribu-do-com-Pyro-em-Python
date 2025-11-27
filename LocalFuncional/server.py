# server.py
from Pyro5.api import expose, behavior, Daemon, locate_ns
import threading
import time

@expose
@behavior(instance_mode="single")
class ChatServer:
    def __init__(self):
        # clientes: nome -> {'uri': uri_str, 'last_seen': timestamp}
        self.clients = {}
        # histórico como lista de dicionários: {from, to, text, ts}
        self.history = []
        self.lock = threading.Lock()

    def register_client(self, name: str, callback_uri: str):
        """Registra um cliente (nome e URI do callback)."""
        with self.lock:
            if name in self.clients:
                return {"ok": False, "error": "nome_ja_em_uso"}
            self.clients[name] = {"uri": callback_uri, "last_seen": time.time()}
            print(f"[server] {name} registrado -> {callback_uri}")
        self._announce_system_message(f"{name} entrou no chat.")
        return {"ok": True}

    def unregister_client(self, name: str):
        with self.lock:
            if name in self.clients:
                del self.clients[name]
                print(f"[server] {name} desregistrado")
            else:
                return {"ok": False, "error": "nao_encontrado"}
        self._announce_system_message(f"{name} saiu do chat.")
        return {"ok": True}

    def send_message(self, from_name: str, to: str, text: str):
        """
        from_name: remetente
        to: destinatário (nome) ou "ALL" para broadcast
        text: string
        """
        ts = time.time()
        msg = {"from": from_name, "to": to, "text": text, "ts": ts}
        with self.lock:
            self.history.append(msg)
        if to == "ALL":
            targets = list(self.clients.items())
        else:
            with self.lock:
                if to not in self.clients:
                    return {"ok": False, "error": "destinatario_nao_encontrado"}
                targets = [(to, self.clients[to])]
        # enviar por callback remoto (não bloqueante em threads)
        for name, info in targets:
            threading.Thread(target=self._deliver, args=(info["uri"], msg, name), daemon=True).start()
        return {"ok": True}

    def get_history(self, limit: int = 100):
        """Retorna último 'limit' itens do histórico."""
        with self.lock:
            return list(self.history[-limit:])

    def list_clients(self):
        with self.lock:
            return list(self.clients.keys())

    def _deliver(self, callback_uri, msg, target_name):
        try:
            # obtém proxy e chama receive (o cliente deve ter um objeto remoto com receive)
            import Pyro5.api as _p
            proxy = _p.Proxy(callback_uri)
            proxy._pyroTimeout = 5  # tempo de espera curto para evitar travar o servidor
            proxy.receive(msg)
        except Exception as e:
            print(f"[server] falha ao enviar para {target_name}: {e}")

    def _announce_system_message(self, text):
        """Mensagem de sistema para todos."""
        self.send_message("SYSTEM", "ALL", text)

if __name__ == "__main__":
    ns = locate_ns()  # procura name server (deve estar rodando)
    with Daemon() as daemon:
        uri = daemon.register(ChatServer())
        ns.register("chat.server", uri)
        print("[server] ChatServer registrado no nameserver como 'chat.server'")
        print("[server] Aguardando requisições...")
        daemon.requestLoop()
