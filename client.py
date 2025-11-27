# client.py

import Pyro5.api
import Pyro5.errors
import threading
import sys

# Configurações LOCAIS (IP da VPN/LAN do Servidor)
NS_HOST = "26.84.123.1"
NS_PORT = 9090

# 1. Objeto Callback do Cliente (RPC Reversa)
@Pyro5.api.expose
class ClienteChatCallback:
    def __init__(self, nome):
        self.nome_usuario = nome

    def receive_message(self, message: str, is_private: bool): 
        """Recebe e exibe a mensagem enviada pelo servidor."""
        prefixo = "[PRIVADO/SISTEMA]" if is_private else ""
        print(f"\n<< {prefixo} {message} >>")
        sys.stdout.flush() 

# 2. Função de Cleanup Isolada
def cleanup_servidor(nome_usuario, host, port):
    """
    Função segura para notificar o servidor da desconexão,
    isolando a chamada RPC para evitar erros de thread ownership.
    """
    try:
        ns_cleanup = Pyro5.api.locate_ns(host=host, port=port)
        uri_servidor_cleanup = ns_cleanup.lookup("ChatService.Server") 
        
        servidor_cleanup = Pyro5.api.Proxy(uri_servidor_cleanup)
        
        # Reivindica a posse no thread atual para evitar o erro de ownership
        servidor_cleanup._pyroClaimOwnership() 

        servidor_cleanup.unregister_client(nome_usuario)
        print(f"[{nome_usuario}] Notificação de desconexão enviada.")
        
    except Pyro5.errors.CommunicationError:
        print("Não foi possível notificar o servidor (servidor fora?).")
    except Pyro5.errors.NamingError:
        print("Name Server inacessível durante desconexão.")
    except Pyro5.errors.PyroError as e:
        # Captura e trata o erro de ownership para evitar o traceback
        if "not the owner of this proxy" in str(e):
             print(f"Aviso: Erro de posse do Proxy capturado durante cleanup.")
        else:
            raise e


# 3. Lógica Principal do Cliente
def iniciar_cliente():
    nome_usuario = input("Digite seu nome de usuário: ").strip()
    if not nome_usuario:
        print("Nome de usuário inválido.")
        return

    cliente_daemon = None
    uri_servidor = None
    
    try:
        # Inicialização do Daemon
        # Força o Daemon a escutar no IP da VPN (necessário para callback)
        cliente_daemon = Pyro5.api.Daemon(host=NS_HOST)
        
        cliente_callback = ClienteChatCallback(nome_usuario)
        cliente_uri = cliente_daemon.register(cliente_callback)
        
        threading.Thread(target=cliente_daemon.requestLoop, daemon=True).start()

        # 1. Obter o URI do Servidor
        print("Buscando Name Server...")
        ns = Pyro5.api.locate_ns(host=NS_HOST, port=NS_PORT)
        uri_servidor = ns.lookup("ChatService.Server") 
            
        # 2. Registrar o usuário no Servidor (Proxy temporário para registro)
        servidor_registro = Pyro5.api.Proxy(uri_servidor)
        sucesso, resposta = servidor_registro.register_client(nome_usuario, cliente_uri) 
        
        if not sucesso:
            print(f"Erro ao registrar: {resposta}")
            return

        print("\n--- CHAT CONECTADO ---")
        print("Comandos: 'exit' para sair, '@<usuário> <mensagem>' para mensagem privada.")
        
        # Loop de Envio de Mensagens
        while True:
            mensagem_input = input(f"[{nome_usuario}] > ").strip()
            
            if mensagem_input.lower() == 'exit':
                break
            
            if not mensagem_input:
                continue

            # 🌟 CORREÇÃO: Crie e reivindique o proxy DENTRO do loop 
            # para garantir que o Thread Principal seja o proprietário exclusivo 
            servidor_loop = Pyro5.api.Proxy(uri_servidor)
            servidor_loop._pyroClaimOwnership() 

            # Lógica de mensagens privadas (@usuario mensagem)
            if mensagem_input.startswith('@'):
                partes = mensagem_input.split(' ', 1)
                destinatario = partes[0][1:].strip() 
                mensagem = partes[1] if len(partes) > 1 else ""
                
                if not destinatario or not mensagem:
                    print("Formato inválido para mensagem privada. Use: @usuario <mensagem>")
                    continue
                
                servidor_loop.send_message(nome_usuario, mensagem, destinatario) 
                
            else:
                # Mensagem pública
                servidor_loop.send_message(nome_usuario, mensagem_input) 

    except Pyro5.errors.CommunicationError as e:
        print(f"\nERRO: Conexão com o servidor perdida: {e}")
    except Pyro5.errors.NamingError:
        print("\nERRO: Não foi possível localizar o Name Server ou o objeto do chat.")
        print(f"Certifique-se de que o Name Server ('pyro5-ns -n {NS_HOST} -p {NS_PORT}') e o Servidor estão rodando.")
    except Exception as e:
        print(f"\nERRO Inesperado: {e}")
    finally:
        
        # 1. ENCERRA O DAEMON DO CLIENTE PRIMEIRO
        if cliente_daemon:
            cliente_daemon.shutdown() 

        # 2. CHAMA A FUNÇÃO DE CLEANUP ISOLADA
        if nome_usuario and uri_servidor:
            cleanup_servidor(nome_usuario, NS_HOST, NS_PORT)
        
        print("Desconectado. Pressione Enter para sair.")


if __name__ == "__main__":
    iniciar_cliente()