from Pyro5.api import expose, behavior, Daemon, locate_ns
import threading
import time

@expose
@behavior(instance_mode="single")
class ChatServer:
    def __init__(self):
        # clientes: nome -> {'uri': uri_str, 'last_seen': timestamp}
        # uri (o endereço remoto do objeto callback do cliente) e last_seen (timestamp da última atualização/registro)
        self.clients = {    }

        # histórico como lista de dicionários: {from, to, text, ts}
        # Armazena todas as mensagens
        self.history = [    ]

        # Bloqueio para evitar condições de corrida
        self.lock = threading.Lock()

    def register_client(self, name: str, callback_uri: str):
        """
        Registra um cliente (nome e URI do callback).
        1. Adquire o lock para garantir acesso exclusivo às estruturas de dados.
        2. Verifica se o 'name' já está em uso; se sim, retorna erro.
        3. Se não estiver em uso, armazena o 'name' como chave, e a 'callback_uri' e o timestamp atual em 'self.clients'.
        4. Libera o lock.
        5. Envia uma mensagem de sistema ("<name> entrou no chat.") para todos os clientes.
        6. Retorna o status de sucesso.
        """
        with self.lock:
            if name in self.clients:
                return {"ok": False, "error": "nome_ja_em_uso"}
            self.clients[name] = {"uri": callback_uri, "last_seen": time.time()}
            print(f"[server] {name} registrado -> {callback_uri}")
        self._announce_system_message(f"{name} entrou no chat.")
        return {"ok": True}

    def unregister_client(self, name: str):
        """
        Desregistra um cliente pelo seu nome.
        1. Adquire o lock.
        2. Verifica se o 'name' está em 'self.clients'.
        3. Se estiver, remove o cliente de 'self.clients' e imprime no console do servidor.
        4. Se não estiver, retorna erro.
        5. Libera o lock.
        6. Envia uma mensagem de sistema ("<name> saiu do chat.") para todos os clientes.
        7. Retorna o status de sucesso.
        """
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
        Processa e envia uma mensagem (P2P ou Broadcast).
        1. Cria o dicionário 'msg' com remetente, destinatário, texto e timestamp.
        2. Adquire o lock e adiciona 'msg' ao 'self.history'.
        3. Define a lista de 'targets' (destinatários) com base no campo 'to':
           a. Se 'to' for "ALL", a lista inclui todos os clientes em 'self.clients'.
           b. Se for um nome específico, verifica se o destinatário existe; se existir, a lista inclui apenas ele. Caso contrário, retorna erro.
        4. Itera sobre os 'targets' e, para cada um:
           a. Inicia uma nova thread (não bloqueante) para chamar o método '_deliver'.
           b. O '_deliver' usará a URI de callback do cliente para enviar a mensagem.
        5. Retorna o status de sucesso.
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
        """
        Retorna o histórico de mensagens.
        1. Adquire o lock para garantir que o histórico não seja modificado durante a leitura.
        2. Retorna uma cópia da porção final da lista 'self.history' (as últimas 'limit' mensagens).
        3. Libera o lock.
        """
        with self.lock:
            return list(self.history[-limit:])

    def list_clients(self):
        """
        Retorna uma lista dos nomes de todos os clientes registrados.
        1. Adquire o lock.
        2. Retorna uma lista (cópia) das chaves (nomes) do dicionário 'self.clients'.
        3. Libera o lock.
        """
        with self.lock:
            return list(self.clients.keys())

    def _deliver(self, callback_uri, msg, target_name):
        """
        Função de entrega de mensagem via callback remoto (executada em uma thread separada).
        1. Tenta criar um 'Proxy' do Pyro5 usando a 'callback_uri' do cliente.
        2. Define um tempo limite curto ('_pyroTimeout = 5') para a chamada remota.
        3. Chama o método 'receive(msg)' no objeto remoto do cliente (callback).
        4. Se a chamada falhar (ex: cliente desconectou), captura a exceção e imprime a falha no console do servidor.
        """
        try:
            # obtém proxy e chama receive (o cliente deve ter um objeto remoto com receive)
            import Pyro5.api as _p
            proxy = _p.Proxy(callback_uri)
            proxy._pyroTimeout = 5  # tempo de espera curto para evitar travar o servidor
            proxy.receive(msg)
        except Exception as e:
            print(f"[server] falha ao enviar para {target_name}: {e}")

    def _announce_system_message(self, text):
        """
        Envia uma mensagem de sistema (SYSTEM) para todos os clientes (ALL).
        1. É um método auxiliar que simplesmente chama 'send_message' usando "SYSTEM" como remetente e "ALL" como destinatário.
        """
        self.send_message("SYSTEM", "ALL", text)

if __name__ == "__main__":
    ns = locate_ns()  # procura name server (deve estar rodando)
    with Daemon(host="192.168.15.3") as daemon:
        uri = daemon.register(ChatServer())
        ns.register("chat.server", uri)
        print("[server] ChatServer registrado no nameserver como 'chat.server'")
        print("[server] Aguardando requisições...")
        daemon.requestLoop()
