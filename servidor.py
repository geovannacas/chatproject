# servidor.py
import socket
import threading
import os

# --- Configurações do Servidor ---
HOST = '127.0.0.1'  # Endereço IP do servidor (localhost)
PORT = 65432  # Porta para escutar conexões

# --- Estruturas de Dados para Gerenciamento ---
clientes = {}  # Dicionário para armazenar clientes conectados {username: conn}
grupos = {}  # Dicionário para armazenar grupos {group_name: [members]}
lock = threading.Lock()  # Lock para garantir acesso seguro às estruturas compartilhadas


# --- Funções Auxiliares ---

def transmitir_mensagem(mensagem, remetente_conn):
    """ Envia uma mensagem para todos os clientes, exceto o remetente. """
    with lock:
        for cliente, conn in clientes.items():
            if conn != remetente_conn:
                try:
                    conn.sendall(mensagem.encode('utf-8'))
                except:
                    # Remove o cliente se a conexão falhar
                    remover_cliente(cliente, conn)


def remover_cliente(username, conn):
    """ Remove um cliente das listas de clientes e grupos. """
    with lock:
        if username in clientes:
            del clientes[username]
        for nome_grupo, membros in grupos.items():
            if username in membros:
                membros.remove(username)
        print(f"[INFO] {username} desconectado.")
        conn.close()


def enviar_arquivo(conn, destinatario, nome_arquivo):
    """ Envia um arquivo para um usuário ou grupo. """
    try:
        tamanho_arquivo = os.path.getsize(nome_arquivo)
        # Informa ao cliente que um arquivo está chegando
        conn.sendall(f"FILE_TRANSFER|{destinatario}|{nome_arquivo}|{tamanho_arquivo}".encode('utf-8'))

        # Envia o arquivo em blocos
        with open(nome_arquivo, 'rb') as f:
            while True:
                bytes_lidos = f.read(4096)
                if not bytes_lidos:
                    break
                conn.sendall(bytes_lidos)
        print(f"[INFO] Arquivo {nome_arquivo} enviado para {destinatario}.")
    except FileNotFoundError:
        conn.sendall(f"ERRO|Arquivo {nome_arquivo} não encontrado.".encode('utf-8'))
    except Exception as e:
        print(f"[ERRO] Falha ao enviar arquivo: {e}")


# --- Lógica Principal de Gerenciamento do Cliente ---

def gerenciar_cliente(conn, addr):
    """ Função executada por cada thread para gerenciar um cliente. """
    print(f"[NOVA CONEXÃO] {addr} conectado.")
    username = None
    try:
        # Autenticação do usuário
        username = conn.recv(1024).decode('utf-8')
        with lock:
            if username in clientes:
                conn.sendall("ERRO|Nome de usuário já em uso. Conexão encerrada.".encode('utf-8'))
                return
            clientes[username] = conn
        print(f"[AUTENTICAÇÃO] Usuário {username} autenticado.")
        conn.sendall("INFO|Conectado ao servidor com sucesso!".encode('utf-8'))

        # Loop principal de recebimento de mensagens
        while True:
            mensagem = conn.recv(1024).decode('utf-8')
            if not mensagem:
                break

            partes = mensagem.split('|')
            comando = partes[0]

            if comando == "MSG":
                destinatario = partes[1]
                conteudo = '|'.join(partes[2:])

                with lock:
                    if destinatario in clientes:  # Mensagem Privada
                        dest_conn = clientes[destinatario]
                        dest_conn.sendall(f"MSG_PRIVADA|{username}|{conteudo}".encode('utf-8'))
                    elif destinatario in grupos:  # Mensagem em Grupo
                        for membro in grupos[destinatario]:
                            if membro != username and membro in clientes:
                                clientes[membro].sendall(
                                    f"MSG_GRUPO|{destinatario}|{username}|{conteudo}".encode('utf-8'))
                    else:
                        conn.sendall(f"ERRO|Usuário ou grupo '{destinatario}' não encontrado.".encode('utf-8'))

            elif comando == "CRIAR_GRUPO":
                nome_grupo = partes[1]
                with lock:
                    if nome_grupo not in grupos:
                        grupos[nome_grupo] = [username]
                        conn.sendall(f"INFO|Grupo '{nome_grupo}' criado com sucesso.".encode('utf-8'))
                    else:
                        conn.sendall(f"ERRO|Grupo '{nome_grupo}' já existe.".encode('utf-8'))

            elif comando == "ENTRAR_GRUPO":
                nome_grupo = partes[1]
                with lock:
                    if nome_grupo in grupos:
                        if username not in grupos[nome_grupo]:
                            grupos[nome_grupo].append(username)
                            conn.sendall(f"INFO|Você entrou no grupo '{nome_grupo}'.".encode('utf-8'))
                        else:
                            conn.sendall(f"ERRO|Você já é membro do grupo '{nome_grupo}'.".encode('utf-8'))
                    else:
                        conn.sendall(f"ERRO|Grupo '{nome_grupo}' não existe.".encode('utf-8'))

            elif comando == "LISTAR":
                with lock:
                    lista_usuarios = "Usuários online: " + ", ".join(clientes.keys())
                    lista_grupos = "Grupos disponíveis: " + ", ".join(grupos.keys())
                    conn.sendall(f"INFO|{lista_usuarios}\nINFO|{lista_grupos}".encode('utf-8'))

            elif comando == "SAIR":
                break

    except Exception as e:
        print(f"[ERRO] Erro com {addr}: {e}")
    finally:
        if username:
            remover_cliente(username, conn)


# --- Função Principal do Servidor ---

def iniciar_servidor():
    """ Inicializa o servidor e aguarda por conexões. """
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind((HOST, PORT))
    servidor.listen()
    print(f"[ESCUTANDO] Servidor escutando em {HOST}:{PORT}")

    while True:
        conn, addr = servidor.accept()
        thread = threading.Thread(target=gerenciar_cliente, args=(conn, addr))
        thread.start()


if __name__ == "__main__":
    iniciar_servidor()