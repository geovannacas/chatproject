# servidor.py
import socket       # Biblioteca padrão para comunicação de rede (sockets)
import threading    # Módulo para gerenciar threads (execução de tarefas em paralelo)
import os           # Módulo para interagir com o sistema operacional (caminhos de arquivo, etc.)

HOST = '172.16.25.37'  # Use o IP da sua máquina na rede local. Como saber? ipconfig no terminal
PORT = 65432

clientes = {}           # {username: conn} Dicionário para mapear nomes de usuários para suas conexões (sockets)
grupos = {}             # {group: [members]} - Dicionário para armazenar os membros de cada grupo
lock = threading.Lock() # Objeto de bloqueio (lock) para sincronização, garantindo que o acesso
                        # a recursos compartilhados (como os dicionários 'clientes' e 'grupos')
                        # seja seguro em ambientes com múltiplas threads

def remover_cliente(username, conn):
    """ Remove cliente da lista e dos grupos """
    with lock:
        clientes.pop(username, None)
        for membros in grupos.values():
            if username in membros:
                membros.remove(username)
    print(f"[INFO] {username} desconectado.")
    try:
        conn.close()
    except:
        pas

def broadcast(mensagem, ignorar=None):
    """ Envia mensagem a todos """
    # Garante que o dicionário de clientes não seja modificado durante a iteração 
    # Criando uma copia da lista de clientes
    with lock: 
        for user, conn in list(clientes.items()):
            if user != ignorar:
                try:
                    conn.sendall(mensagem.encode('utf-8'))
                except:
                    remover_cliente(user, conn)

def envia_mensagem(partes, username, conn):
    # Lida com mensagens privadas e de grupo
    destino, conteudo = partes[1], '|'.join(partes[2:])
    if destino in clientes:
        # Envia a mensagem para outro cliente
        clientes[destino].sendall(
            f"MSG_PRIVADA|{username}|{conteudo}".encode('utf-8')
        )
    elif destino in grupos:
        # Verifica se o remetente faz parte do grupo
        if username not in grupos[destino]:
            conn.sendall(
                f"ERRO|Você não faz parte do grupo '{destino}'.".encode('utf-8')
            )
            return
        # Envia a mensagem para cada membro do grupo
        for membro in grupos[destino]:
            if membro != username:
                clientes[membro].sendall(
                    f"MSG_GRUPO|{destino}|{username}|{conteudo}".encode('utf-8')
                )
    else:
        conn.sendall(
            f"ERRO|Destino '{destino}' não encontrado.".encode('utf-8')
        )

def criar_grupo(partes, username, conn):
     # Par criar grupos
    nome = partes[1]
    # verifica se o grupo já existe
    if nome not in grupos:
        grupos[nome] = [username]
        broadcast(f"INFO|Grupo {nome} criado por {username}")
    else:
        conn.sendall("ERRO|Grupo já existe.".encode('utf-8'))

def entrar_grupo(partes, username, conn):
    nome = partes[1]
    if nome in grupos and username not in grupos[nome]:
        grupos[nome].append(username)
        conn.sendall(f"INFO|Você entrou no grupo '{nome}'.".encode('utf-8'))
    else:
        conn.sendall("ERRO|Não foi possível entrar no grupo.".encode('utf-8'))

def adicionar_grupo(partes, username, conn):
    user_add, grupo = partes[1], partes[2]
    if grupo in grupos and username in grupos[grupo] and user_add in clientes:
        grupos[grupo].append(user_add)
        clientes[user_add].sendall(
            f"INFO|Você foi adicionado no grupo {grupo} por {username}".encode('utf-8'))
    else:
        conn.sendall("ERRO|Falha ao adicionar.".encode('utf-8'))

def lista_membros(partes, conn):
    grupo = partes[1]
    if grupo in grupos:
        membros = ", ".join(grupos[grupo])
        conn.sendall(f"INFO|Membros do grupo {grupo}: {membros}".encode('utf-8'))
    else:
        conn.sendall("ERRO|Grupo não existe.".encode('utf-8'))

def sair_grupo(partes, username, conn):
    grupo = partes[1]
    if grupo in grupos and username in grupos[grupo]:
        grupos[grupo].remove(username)
        conn.sendall(f"INFO|Você saiu do grupo {grupo}".encode('utf-8'))

def apagar_grupo(partes, username, conn):
    grupo = partes[1]
    if grupo in grupos and username in grupos[grupo]:
        del grupos[grupo]
        broadcast(f"INFO|Grupo {grupo} apagado por {username}")
    else:
        conn.sendall("ERRO|Você não pode apagar esse grupo.".encode('utf-8'))

def listar_usuarios_e_grupos(conn):
    usuarios = "Usuários: " + ", ".join(clientes.keys())
    grupos_list = "Grupos: " + ", ".join(grupos.keys())
    conn.sendall(f"INFO|{usuarios}\nINFO|{grupos_list}".encode('utf-8'))

def enviar_arquivo(partes, username, conn):
    try:
        destino, nome_arquivo, tamanho = partes[1], partes[2], int(partes[3])
        # confirma ao remetente que o servidor está pronto para receber
        conn.sendall("OK_ARQUIVO".encode('utf-8'))

        bytes_recebidos = 0
        # Escolha de destino(s)
        destinatarios = []
        if destino in clientes:
            destinatarios = [clientes[destino]]
        elif destino in grupos:
            destinatarios = [clientes[m] for m in grupos[destino] if m != username]

        # Opcional: envie um cabeçalho para os destinatários antes dos dados
        for sock_dest in destinatarios:
            try:
                sock_dest.sendall(f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
            except Exception as e:
                print(f"[WARN] Não foi possível enviar header para destinatário: {e}")

        # Agora leia do remetente em chunks e retransmita imediatamente
        while bytes_recebidos < tamanho:
            to_read = min(4096, tamanho - bytes_recebidos)
            pacote = conn.recv(to_read)
            if not pacote:
                raise ConnectionError("Conexão encerrada no meio do envio")
            bytes_recebidos += len(pacote)

            # retransmite o chunk para cada destinatário
            for sock_dest in destinatarios:
                try:
                    sock_dest.sendall(pacote)
                except Exception as e:
                    # Se um destinatário estiver lento, registramos e continuamos.
                    # Em alternativa, poderíamos colocar esse destinatário numa fila e continuar com os demais.
                    print(f"[WARN] Falha ao enviar chunk para um destinatário: {e}")

        # opcional: enviar ack ao remetente antes ou depois do encaminhamento
        conn.sendall("ARQUIVO_OK".encode('utf-8'))

    except Exception as e:
        print(f"[ERRO ARQUIVO] com {username}: {e}")
        try:
            conn.sendall(f"ERRO|Falha ao transferir arquivo: {e}".encode('utf-8'))
        except:
            pass

def handle_usuario(addr, conn):
    while True:
        try:
            username_candidato = conn.recv(1024).decode('utf-8')
            if not username_candidato:
                print(f"[INFO] Conexão de {addr} encerrada antes de definir usuário.")
                return None

            with lock:
                if username_candidato in clientes:
                    conn.sendall(
                        f"O nome '{username_candidato}' já está em uso, escolha outro.".encode('utf-8')
                    )
                else:
                    clientes[username_candidato] = conn
                    conn.sendall("NOME_OK".encode('utf-8'))
                    return username_candidato

        except ConnectionResetError:
            print(f"[INFO] Conexão de {addr} resetada durante definição do nome.")
            conn.close()
            return None

def handle_acoes(username, conn):
    while True:
        msg = conn.recv(4096).decode('utf-8')
        if not msg:
            break

        partes = msg.split('|')
        comando = partes[0]

        match comando:
            case "MSG":
                envia_mensagem(partes, username, conn)

            case "CRIAR_GRUPO":
                criar_grupo(partes, username, conn)

            case "ENTRAR_GRUPO":
                entrar_grupo(partes, username, conn)

            case "ADD_GRUPO":
                adicionar_grupo(partes, username, conn)

            case "MEMBROS":
                lista_membros(partes, conn)

            case "SAIR_GRUPO":
                sair_grupo(partes, username, conn)

            case "APAGAR_GRUPO":
                apagar_grupo()

            case "LISTAR":
                listar_usuarios_e_grupos(conn)

            case "SAIR":
                break

            case "ARQUIVO":
                enviar_arquivo(partes, username, conn)

            case _:
                # comando desconhecido
                print(f"[WARN] comando desconhecido de {username}: {comando}")    

# --- Lógica Cliente ---
def gerenciar_cliente(conn, addr):
    username = handle_usuario(username, addr, conn)
    print(f"[NOVA CONEXÃO] {username} ({addr}) conectado.")
    print(f"[SERVIDOR] {len(clientes)} clientes conectados, {len(grupos)} grupos criados")
    try:
        handle_acoes(username, conn)
    except ConnectionResetError:
        print(f"[INFO] {username} desconectou abruptamente.")
    except Exception as e:
        print(f"[ERRO] {username}: {e}")
    finally:
        if username:
            remover_cliente(username, conn)

# --- Iniciar Servidor ---
def iniciar_servidor():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind((HOST, PORT))
    servidor.listen()
    print(f"[SERVIDOR] Escutando em {HOST}:{PORT}")
    while True:
        # Aceita uma nova conexão
        conn, addr = servidor.accept()
        # Cria e inicia uma nova thread para gerenciar a conexão com o cliente recém-conectado
        # Isso permite que o servidor lide com múltiplos clientes simultaneamente
        threading.Thread(target=gerenciar_cliente, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    iniciar_servidor()
