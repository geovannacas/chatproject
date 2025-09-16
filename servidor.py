# servidor.py
import socket       # Biblioteca padrão para comunicação de rede (sockets)
import threading    # Módulo para gerenciar threads (execução de tarefas em paralelo)
import os           # Módulo para interagir com o sistema operacional (caminhos de arquivo, etc.)

HOST = '10.1.5.60'  # Use o IP da sua máquina na rede local. Como saber? ipconfig no terminal
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
        pass


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


# --- Lógica Cliente ---
def gerenciar_cliente(conn, addr):
    username = None
    while True:
        try:
            # Loop para autenticação do nome de usuário
            # Só pode ter um unico username
            username_candidato = conn.recv(1024).decode('utf-8')
            if not username_candidato:
                print(f"[INFO] Conexão de {addr} encerrada antes de definir usuário.")
                return
            with lock:
                if username_candidato in clientes:
                    conn.sendall(
                        f"O nome escolhido '{username_candidato}' já está em uso, por favor escolher outro nome".encode(
                            'utf-8'))
                else:
                    username = username_candidato  # Define o username final
                    clientes[username] = conn
                    conn.sendall("NOME_OK".encode('utf-8'))
                    break
        except ConnectionResetError:
            print(f"[INFO] Conexão de {addr} resetada durante a definição do nome.")
            conn.close()
            return

    print(f"[NOVA CONEXÃO] {username} ({addr}) conectado.")
    print(f"[SERVIDOR] {len(clientes)} clientes conectados, {len(grupos)} grupos criados")

    try:
        while True:
            msg = conn.recv(4096).decode('utf-8')
            if not msg: break

            partes = msg.split('|')
            comando = partes[0]

            if comando == "MSG":
                # Lida com mensagens privadas e de grup
                destino, conteudo = partes[1], '|'.join(partes[2:])
                if destino in clientes:
                    # Envia a mensagem para outro cliente
                    clientes[destino].sendall(f"MSG_PRIVADA|{username}|{conteudo}".encode('utf-8'))
                elif destino in grupos:
                    # Envia a mensagem para cada membro do grupo
                    for membro in grupos[destino]:
                        if membro != username:
                            clientes[membro].sendall(f"MSG_GRUPO|{destino}|{username}|{conteudo}".encode('utf-8'))
                else:
                    conn.sendall(f"ERRO|Destino '{destino}' não encontrado.".encode('utf-8'))

            elif comando == "CRIAR_GRUPO":
                # Par criar grupos
                nome = partes[1]
                # verifica se o grupo já existe
                if nome not in grupos:
                    grupos[nome] = [username]
                    broadcast(f"INFO|Grupo {nome} criado por {username}")
                else:
                    conn.sendall("ERRO|Grupo já existe.".encode('utf-8'))

            elif comando == "ENTRAR_GRUPO":
                nome = partes[1]
                if nome in grupos and username not in grupos[nome]:
                    grupos[nome].append(username)
                    conn.sendall(f"INFO|Você entrou no grupo '{nome}'.".encode('utf-8'))
                else:
                    conn.sendall("ERRO|Não foi possível entrar no grupo.".encode('utf-8'))

            elif comando == "ADD_GRUPO":
                user_add, grupo = partes[1], partes[2]
                if grupo in grupos and username in grupos[grupo] and user_add in clientes:
                    grupos[grupo].append(user_add)
                    clientes[user_add].sendall(
                        f"INFO|Você foi adicionado no grupo {grupo} por {username}".encode('utf-8'))
                else:
                    conn.sendall("ERRO|Falha ao adicionar.".encode('utf-8'))

            elif comando == "MEMBROS":
                grupo = partes[1]
                if grupo in grupos:
                    membros = ", ".join(grupos[grupo])
                    conn.sendall(f"INFO|Membros do grupo {grupo}: {membros}".encode('utf-8'))
                else:
                    conn.sendall("ERRO|Grupo não existe.".encode('utf-8'))

            elif comando == "SAIR_GRUPO":
                grupo = partes[1]
                if grupo in grupos and username in grupos[grupo]:
                    grupos[grupo].remove(username)
                    conn.sendall(f"INFO|Você saiu do grupo {grupo}".encode('utf-8'))

            elif comando == "APAGAR_GRUPO":
                grupo = partes[1]
                if grupo in grupos and username in grupos[grupo]:
                    del grupos[grupo]
                    broadcast(f"INFO|Grupo {grupo} apagado por {username}")
                else:
                    conn.sendall("ERRO|Você não pode apagar esse grupo.".encode('utf-8'))

            elif comando == "LISTAR":
                usuarios = "Usuários: " + ", ".join(clientes.keys())
                grupos_list = "Grupos: " + ", ".join(grupos.keys())
                conn.sendall(f"INFO|{usuarios}\nINFO|{grupos_list}".encode('utf-8'))

            elif comando == "SAIR":
                break

            elif comando == "ARQUIVO":
                try:
                    destino, nome_arquivo, tamanho = partes[1], partes[2], int(partes[3])
                    conn.sendall("OK_ARQUIVO".encode('utf-8'))

                    dados = b""
                    bytes_recebidos = 0
                    while bytes_recebidos < tamanho:
                        # Recebe os dados do arquivo em pedaços do cliente
                        pacote = conn.recv(min(4096, tamanho - bytes_recebidos))
                        if not pacote:
                            raise ConnectionError("Conexão encerrada no meio do envio")
                        dados += pacote
                        bytes_recebidos += len(pacote)

                    if destino in clientes:
                        # Se o destino é um usuário, retransmite a metainformação e os dados binários
                        clientes[destino].sendall(f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
                        clientes[destino].sendall(dados)
                    elif destino in grupos:
                        # Se o destino é um grupo, retransmite para cada membr
                        for membro in grupos[destino]:
                            if membro != username:
                                clientes[membro].sendall(
                                    f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
                                clientes[membro].sendall(dados)

                    conn.sendall("ARQUIVO_OK".encode('utf-8'))
                except Exception as e:
                    print(f"[ERRO ARQUIVO] com {username}: {e}")
                    conn.sendall(f"ERRO|Falha ao transferir arquivo: {e}".encode('utf-8'))

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
