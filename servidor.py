# servidor.py (chat_server.py)

import Pyro5.api
import Pyro5.errors
import threading
import time

# Configurações LOCAIS (devem corresponder às do cliente)
NS_HOST = "26.84.123.1"
NS_PORT = 9090
SERVER_HOST = "26.84.123.1" # Onde o daemon do servidor irá escutar

@Pyro5.api.expose
class ChatServer:
    def __init__(self):
        # Dicionário para armazenar clientes: {username: client_proxy}
        # O client_proxy é o objeto remoto (callback) do cliente
        self.clients = {}
        print("Servidor de Chat inicializado.")

    def register_client(self, username: str, client_uri): # Nome corrigido: register_client
        """Registra um novo cliente e notifica os demais."""
        if username in self.clients:
            print(f"Usuário {username} tentou se conectar, mas já está online.")
            return False, f"O usuário '{username}' já está conectado." 

        try:
            client_proxy = Pyro5.api.Proxy(client_uri)
        except Exception as e:
             # Se a URI for inválida ou inacessível, retorna erro.
             return False, f"Falha ao criar proxy para o cliente: {e}"
        

        self.clients[username] = client_proxy
        print(f"Usuário **{username}** conectado. Total: {len(self.clients)}")
        
        # Notificar todos sobre o novo usuário
        self.broadcast_system_message(f"O usuário **{username}** entrou no chat.")
        return True, "Registro bem-sucedido." # Retorna sucesso

    def unregister_client(self, username: str): # Nome corrigido: unregister_client
        """Remove um cliente e notifica os demais."""
        if username in self.clients:
            del self.clients[username]
            print(f"Usuário **{username}** desconectado. Total: {len(self.clients)}")
            
            # Notificar todos sobre a saída
            self.broadcast_system_message(f"O usuário **{username}** saiu do chat.")

    def send_message(self, sender: str, message: str, recipient: str = None): # Nome corrigido: send_message, Parâmetro 'recipient' como opcional
        """
        Envia uma mensagem. 
        Se 'recipient' for None, envia para todos (broadcast).
        """
        if recipient and recipient != "TODOS": # Tratamento para mensagem privada
            # Mensagem Privada
            if recipient in self.clients:
                
                # Mensagem que o destinatário vê
                dest_msg = f"[MENSAGEM PRIVADA de {sender}]: {message}"
                # Mensagem de confirmação que o remetente vê
                sender_confirmation = f"[Você -> {recipient}]: {message}"

                try:
                    # Envia a mensagem para o destinatário (True = privado)
                    self.clients[recipient].receive_message(dest_msg, True)
                    # Envia uma confirmação para o remetente (True = privado/sistema)
                    self.clients[sender].receive_message(sender_confirmation, True)
                    print(f"Mensagem privada enviada: {sender} -> {recipient}")
                except Pyro5.errors.CommunicationError:
                    print(f"Erro ao enviar para {recipient}. Usuário desconectado.")
                    self.unregister_client(recipient)
            else:
                # Informa o remetente que o destinatário não foi encontrado
                if sender in self.clients:
                    self.clients[sender].receive_message(f"[ERRO] Usuário '{recipient}' não encontrado ou desconectado.", True)
        else:
            # Mensagem Pública (Broadcast)
            full_msg = f"<{sender}>: {message}"
            self.broadcast_message(sender, full_msg) # Não precisa do 'private=False' aqui
            print(f"Mensagem de broadcast enviada por {sender}")

    def get_online_users(self):
        """Retorna a lista de nomes de usuários online."""
        return list(self.clients.keys())

    def broadcast_message(self, sender: str, message: str): # Simplificado
        """Envia a mensagem para todos os clientes, exceto o remetente."""
        for username, client_proxy in list(self.clients.items()): 
            if username != sender:
                try:
                    client_proxy.receive_message(message, False) # False para mensagem pública
                except Pyro5.errors.CommunicationError:
                    print(f"Erro de comunicação com {username}. Removendo.")
                    self.unregister_client(username)

    def broadcast_system_message(self, message: str):
        """Envia uma mensagem de sistema para todos."""
        system_msg = f"[SISTEMA] {message}"
        # Usa list() para iterar enquanto o unregister_client pode modificar o dicionário
        for username, client_proxy in list(self.clients.items()): 
            try:
                # Mensagens de sistema são tratadas como públicas (False)
                client_proxy.receive_message(system_msg, False) 
            except Pyro5.errors.CommunicationError as e:
                # Se o cliente falhar, remove-o
                print(f"Erro de comunicação com {username} durante msg de sistema. Removendo.")
                self.unregister_client(username)


def start_server():
    daemon = None
    try:
        # Inicializa o Name Server Proxy
        ns = Pyro5.api.locate_ns(host=NS_HOST, port=NS_PORT)
        
        # Inicializa o Daemon do Servidor de Chat (escutando no host local)
        daemon = Pyro5.api.Daemon(host=SERVER_HOST)
        
        # Cria e registra a instância do servidor no Daemon
        chat_server = ChatServer()
        uri = daemon.register(chat_server)
        
        # Registra a URI no Name Server com o nome que o cliente espera
        # NOME DO SERVIÇO CORRIGIDO para "ChatService.Server"
        ns.register("ChatService.Server", uri) 
        
        print(f"Servidor de Chat em execução em: {uri}")
        print("Aguardando conexões...")
        
        # Inicia o loop principal do Daemon
        daemon.requestLoop()

    except Pyro5.errors.NamingError:
        print("\nERRO: Name Server não encontrado.")
        print("Certifique-se de que o Name Server esteja em execução com 'pyro5-ns -n 127.0.0.1 -p 9090'")
    except Exception as e:
        print(f"Erro fatal no servidor: {e}")
    finally:
        if daemon:
            daemon.close()
        print("Servidor encerrado.")

if __name__ == "__main__":
    start_server()