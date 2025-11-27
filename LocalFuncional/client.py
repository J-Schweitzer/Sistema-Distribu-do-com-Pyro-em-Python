import threading
import time
from Pyro5.api import expose, Daemon, Proxy, locate_ns

@expose
class ClientCallback:
    """
    Objeto Remoto Local (Callback)
    Esta classe é exposta remotamente (Pyro5) para que o SERVIDOR possa chamá-la
    e enviar mensagens de volta para o cliente.
    """
    def __init__(self, on_receive):
        # on_receive: função local para exibir/armazenar mensagem
        # Armazena a função que lida com a exibição da mensagem recebida no console local.
        self.on_receive = on_receive

    def receive(self, msg):
        # este método será chamado pelo servidor remoto (callback)
        # Quando o servidor chama esta função remotamente, ela repassa a mensagem (msg)
        # para a função local 'on_receive' para ser exibida na tela.
        self.on_receive(msg)

def interactive_loop(server_proxy, my_name, callback_uri):
    """
    Loop Principal de Interação com o Usuário
    Gerencia a entrada de comandos do usuário e chama os métodos remotos do servidor.
    """
    print(f"Bem-vindo(a), {my_name}!\nComandos:\n  /msg <user> <texto>  -> mensagem privada\n  /all <texto>         -> broadcast\n  /list                -> lista usuários\n  /hist [n]            -> histórico (últimos n)\n  /quit                -> sair\n")
    
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            line = "/quit"  # Trata Ctrl+D ou desconexão forçada como /quit
            
        if not line:
            continue

        # Lógica para processar os comandos do usuário
        if line.startswith("/msg "):
            # Envio de mensagem privada (P2P)
            parts = line.split(" ", 2)
            if len(parts) < 3:
                print("Uso: /msg <user> <texto>")
                continue
            to = parts[1]
            text = parts[2]
            # Chama o método remoto 'send_message' no servidor
            r = server_proxy.send_message(my_name, to, text)
            if not r.get("ok"):
                print("Erro:", r.get("error"))
                
        elif line.startswith("/all "):
            # Envio de mensagem para todos (Broadcast)
            text = line[5:]
            # Chama o método remoto 'send_message' no servidor, usando "ALL" como destinatário
            server_proxy.send_message(my_name, "ALL", text)
            
        elif line == "/list":
            # Listagem de usuários
            # Chama o método remoto 'list_clients' no servidor
            users = server_proxy.list_clients()
            print("Usuários conectados:", users)
            
        elif line.startswith("/hist"):
            # Exibição do histórico de mensagens
            parts = line.split()
            # Pega o número de mensagens a exibir (padrão é 50)
            n = int(parts[1]) if len(parts) > 1 else 50
            # Chama o método remoto 'get_history' no servidor
            h = server_proxy.get_history(n)
            # Formata e exibe cada mensagem do histórico
            for m in h:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m["ts"]))
                print(f"[{ts}] {m['from']} -> {m['to']}: {m['text']}")
                
        elif line == "/quit":
            # Comando de saída
            print("Saindo...")
            # Chama o método remoto 'unregister_client' no servidor
            server_proxy.unregister_client(my_name)
            break
            
        else:
            print("Comando desconhecido.")

def start_client(name):
    """
    Configuração e inicialização do cliente Pyro5.
    """
    
    ns = locate_ns(host = "192.168.15.3")

    # 1. Conexão ao Servidor de Nomes (Name Server)
    # 2. Localização do Servidor de Chat
    server_uri = ns.lookup("chat.server")
    # 3. Criação de um Proxy para o Objeto Remoto do Servidor
    server = Proxy(server_uri)
    
    # Função que será usada pela classe ClientCallback para exibir mensagens na tela.
    def on_receive(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg["ts"]))
        # Exibe a mensagem de forma formatada e garante que o prompt (>) seja redesenhado.
        if msg["to"] == "ALL":
            print(f"\n[{ts}] {msg['from']} (ALL): {msg['text']}\n> ", end="", flush=True)
        else:
            print(f"\n[{ts}] {msg['from']} -> {msg['to']}: {msg['text']}\n> ", end="", flush=True)

    # Criação do Daemon Local para receber Callbacks
    with Daemon(host="192.168.15.6") as daemon:
        # 1. Cria a instância do objeto callback com a função 'on_receive'.
        callback = ClientCallback(on_receive)
        # 2. Registra o objeto callback no Daemon local, obtendo sua URI.
        callback_uri = daemon.register(callback)
        
        # 3. Registro no Servidor Remoto
        # Envia o nome do cliente e a URI do seu objeto de callback para o servidor.
        r = server.register_client(name, callback_uri)
        if not r.get("ok"):
            print("Erro ao registrar:", r)
            return
            
        # 4. Início do Daemon em uma Thread
        # O loop de requisições do Daemon deve rodar em uma thread separada para que 
        # a thread principal possa executar o 'interactive_loop' (interface de usuário).
        daemon_thread = threading.Thread(target=daemon.requestLoop, daemon=True)
        daemon_thread.start()
        
        try:
            # 5. Início do Loop Interativo (Bloqueia a Thread Principal)
            interactive_loop(server, name, callback_uri)
            
        finally:
            # 6. Lógica de Limpeza (Executada ao sair do loop interativo ou em caso de erro)
            try:
                # Tenta desregistrar o cliente do servidor antes de fechar
                server.unregister_client(name)
            except:
                pass
            # Desliga o Daemon local de callback
            daemon.shutdown()
            # Espera a thread do Daemon terminar.
            daemon_thread.join(timeout=1)

if __name__ == "__main__":
    """
    Bloco de Execução Principal
    Verifica os argumentos da linha de comando e inicia o cliente.
    """
    import sys
    if len(sys.argv) != 2:
        print("Uso: python client.py <seu_nome>")
        sys.exit(1)
    # Inicia a aplicação cliente com o nome fornecido no argumento.
    start_client(sys.argv[1])