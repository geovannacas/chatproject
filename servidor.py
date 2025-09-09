# servidor.py
import socket
import threading
import os

HOST = '10.1.5.60'
PORT = 65432

clientes = {}   # {username: conn}
grupos = {}     # {group: [members]}
lock = threading.Lock()

# --- Auxiliares ---
def remover_cliente(username, conn):
    """ Remove cliente da lista e dos grupos """
    with lock:
        clientes.pop(username, None)
        for membros in grupos.values():
            if username in membros:
                membros.remove(username)
    print(f"[INFO] {username} desconectado.")
    conn.close()

def broadcast(mensagem, ignorar=None):
    """ Envia mensagem a todos """
    with lock:
        for user, conn in clientes.items():
            if user != ignorar:
                try:
                    conn.sendall(mensagem.encode('utf-8'))
                except:
                    remover_cliente(user, conn)

# --- Lógica Cliente ---
def gerenciar_cliente(conn, addr):
    while True:
        username = conn.recv(1024).decode('utf-8')
        with lock:
            if username in clientes:
                conn.sendall(f"O nome escolhido '{username}' já está em uso, por favor escolher outro nome".encode('utf-8'))
            else:
                clientes[username] = conn
                conn.sendall("NOME_OK".encode('utf-8'))
                break
        clientes[username] = conn

    print(f"[NOVA CONEXÃO] {username} ({addr}) conectado.")
    # conn.sendall("INFO|Conectado com sucesso.".encode('utf-8'))

    try:
        while True:
            msg = conn.recv(4096).decode('utf-8')
            if not msg: break

            partes = msg.split('|')
            comando = partes[0]

            if comando == "MSG":
                destino, conteudo = partes[1], '|'.join(partes[2:])
                if destino in clientes:  # privado
                    clientes[destino].sendall(f"MSG_PRIVADA|{username}|{conteudo}".encode('utf-8'))
                elif destino in grupos:  # grupo
                    for membro in grupos[destino]:
                        if membro != username:
                            clientes[membro].sendall(f"MSG_GRUPO|{destino}|{username}|{conteudo}".encode('utf-8'))
                else:
                    conn.sendall(f"ERRO|Destino '{destino}' não encontrado.".encode('utf-8'))

            elif comando == "CRIAR_GRUPO":
                nome = partes[1]
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
                    clientes[user_add].sendall(f"INFO|Você foi adicionado no grupo {grupo} por {username}".encode('utf-8'))
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
                destino, nome_arquivo, tamanho = partes[1], partes[2], int(partes[3])
                conn.sendall("OK_ARQUIVO".encode('utf-8'))

                dados = b""
                try:
                    while len(dados) < tamanho:
                        pacote = conn.recv(min(4096, tamanho - len(dados)))
                        if not pacote:
                            raise ConnectionError("Conexão encerrada no meio do envio")
                        dados += pacote

                    # repassa para o destino
                    if destino in clientes:
                        clientes[destino].sendall(f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
                        clientes[destino].sendall(dados)
                    elif destino in grupos:
                        for membro in grupos[destino]:
                            if membro != username:
                                clientes[membro].sendall(f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
                                clientes[membro].sendall(dados)

                    conn.sendall("ARQUIVO_OK".encode('utf-8'))

                except Exception as e:
                    conn.sendall(f"ERRO|Falha ao transferir arquivo: {e}".encode('utf-8'))

    except Exception as e:
        print(f"[ERRO] {username}: {e}")
    finally:
        remover_cliente(username, conn)

# --- Iniciar Servidor ---
def iniciar_servidor():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind((HOST, PORT))
    servidor.listen()
    print(f"[SERVIDOR] Escutando em {HOST}:{PORT}")
    while True:
        conn, addr = servidor.accept()
        threading.Thread(target=gerenciar_cliente, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    iniciar_servidor()
