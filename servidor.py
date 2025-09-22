# servidor.py
import socket  # Biblioteca padrão para comunicação de rede (sockets)
import threading  # Módulo para gerenciar threads (execução de tarefas em paralelo)
import os  # Módulo para interagir com o sistema operacional (caminhos de arquivo, etc.)
from pymongo import MongoClient  # Importar o MongoClient para o DB
from dotenv import load_dotenv

# --- Carrega as variáveis de ambiente do arquivo .env ---
load_dotenv()

# --- Configuração do MongoDB ---
# Pega a URI do MongoDB a partir da variável de ambiente
MONGO_URI = os.getenv("MONGO_URI")

# Verifica se a variável foi carregada corretamente
if not MONGO_URI:
    print("[ERRO FATAL] A variável de ambiente MONGO_URI não foi encontrada.")
    print("Verifique se você criou o arquivo .env e o configurou corretamente.")
    exit()

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client['ChatProject']  # Nome do banco de dados
    grupos_collection = db['grupos']  # Coleção (tabela) para os grupos
    mensagens_collection = db['mensagens']  # Coleção para as mensagens
    print("[DB] Conexão com o MongoDB estabelecida com sucesso.")
except Exception as e:
    print(f"[ERRO DB] Não foi possível conectar ao MongoDB: {e}")
    exit()

# --- Configurações do Servidor ---
HOST = '192.168.6.237'  # ipconfig
PORT = 65432

clientes = {}  # {username: conn} Dicionário para mapear nomes de usuários para suas conexões (sockets)
grupos = {}  # {group: [members]} - Dicionário para armazenar os membros de cada grupo
lock = threading.Lock()  # Objeto de bloqueio (lock) para sincronização, garantindo que o acesso


# a recursos compartilhados (como os dicionários 'clientes' e 'grupos')
# seja seguro em ambientes com múltiplas threads

# --- Função para carregar dados do DB na inicialização ---
def carregar_dados_do_db():
    """ Carrega os grupos do MongoDB para a memória na inicialização do servidor. """
    with lock:
        grupos.clear()
        for grupo_doc in grupos_collection.find():
            nome_grupo = grupo_doc.get('nome')
            membros = grupo_doc.get('membros', [])
            if nome_grupo:
                grupos[nome_grupo] = membros
    print(f"[DB] {len(grupos)} grupos carregados do banco de dados para a memória.")


def remover_cliente(username, conn):
    """ Remove cliente da lista e dos grupos """
    with lock:
        clientes.pop(username, None)
        # A remoção do membro do grupo no DB acontece na função 'sair_grupo'
        for membros in grupos.values():
            if username in membros:
                membros.remove(username)
    # Notifica a todos que o usuário saiu
    broadcast(f"INFO|{username} saiu do chat.", ignorar=username)
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
                    # Se houver erro ao enviar, remove o cliente problemático
                    remover_cliente(user, conn)


def envia_mensagem(partes, username, conn):
    # Lida com mensagens privadas e de grupo
    destino, conteudo = partes[1], '|'.join(partes[2:])

    # [DB] Prepara o documento da mensagem para salvar no MongoDB
    mensagem_doc = {
        'remetente': username,
        'conteudo': conteudo,
        'timestamp': threading.TIMEOUT_MAX  # Idealmente, use: from datetime import datetime; datetime.utcnow()
    }

    if destino in clientes:
        # Envia a mensagem para outro cliente
        mensagem_doc['tipo'] = 'privada'
        mensagem_doc['destinatario'] = destino
        clientes[destino].sendall(
            f"MSG_PRIVADA|{username}|{conteudo}".encode('utf-8')
        )
    elif destino in grupos:
        # Verifica se o remetente faz parte do grupo
        if username not in grupos.get(destino, []):
            conn.sendall(
                f"ERRO|Você não faz parte do grupo '{destino}'.".encode('utf-8')
            )
            return

        mensagem_doc['tipo'] = 'grupo'
        mensagem_doc['grupo'] = destino

        # Envia a mensagem para cada membro do grupo
        for membro in grupos[destino]:
            if membro != username and membro in clientes:
                clientes[membro].sendall(
                    f"MSG_GRUPO|{destino}|{username}|{conteudo}".encode('utf-8')
                )
    else:
        conn.sendall(
            f"ERRO|Destino '{destino}' não encontrado.".encode('utf-8')
        )
        return  # [DB] Não salva a mensagem se o destino não for válido

    # [DB] Salva a mensagem no MongoDB
    try:
        mensagens_collection.insert_one(mensagem_doc)
    except Exception as e:
        print(f"[ERRO DB] Falha ao salvar mensagem: {e}")


def criar_grupo(partes, username, conn):
    # Para criar grupos
    nome_grupo = partes[1]
    with lock:
        # verifica se o grupo já existe
        if nome_grupo in grupos:
            conn.sendall("ERRO|Grupo já existe.".encode('utf-8'))
            return

        # Atualiza em memória
        grupos[nome_grupo] = [username]

        # [DB] Persiste no MongoDB
        try:
            grupos_collection.insert_one({'nome': nome_grupo, 'membros': [username]})
            broadcast(f"INFO|Grupo {nome_grupo} criado por {username}")
        except Exception as e:
            print(f"[ERRO DB] Falha ao criar grupo no DB: {e}")
            conn.sendall("ERRO|Falha interna ao criar grupo.".encode('utf-8'))
            grupos.pop(nome_grupo, None)  # Reverte


def entrar_grupo(partes, username, conn):
    nome_grupo = partes[1]
    with lock:
        if nome_grupo in grupos and username not in grupos[nome_grupo]:
            grupos[nome_grupo].append(username)

            # [DB] Atualiza no MongoDB
            try:
                grupos_collection.update_one(
                    {'nome': nome_grupo},
                    {'$addToSet': {'membros': username}}
                )
                conn.sendall(f"INFO|Você entrou no grupo '{nome_grupo}'.".encode('utf-8'))
            except Exception as e:
                print(f"[ERRO DB] Falha ao entrar no grupo no DB: {e}")
                grupos[nome_grupo].remove(username)  # Reverte
        else:
            conn.sendall("ERRO|Não foi possível entrar no grupo.".encode('utf-8'))


def adicionar_grupo(partes, username, conn):
    user_add, grupo = partes[1], partes[2]
    with lock:
        if grupo not in grupos:
            conn.sendall(f"ERRO|O grupo '{grupo}' não existe.".encode('utf-8'))
            return
        if username not in grupos[grupo]:
            conn.sendall(f"ERRO|Você não é membro do grupo '{grupo}'.".encode('utf-8'))
            return
        if user_add not in clientes:
            conn.sendall(f"ERRO|O usuário '{user_add}' não está online.".encode('utf-8'))
            return
        if user_add in grupos[grupo]:
            conn.sendall(f"ERRO|O usuário '{user_add}' já está no grupo.".encode('utf-8'))
            return

        # Se todas as verificações passaram, adiciona o usuário
        grupos[grupo].append(user_add)
        try:
            grupos_collection.update_one(
                {'nome': grupo},
                {'$addToSet': {'membros': user_add}}
            )
            clientes[user_add].sendall(
                f"INFO|Você foi adicionado ao grupo '{grupo}' por {username}".encode('utf-8'))
            conn.sendall(
                f"INFO|{user_add} foi adicionado ao grupo '{grupo}'.".encode('utf-8'))
        except Exception as e:
            print(f"[ERRO DB] Falha ao adicionar ao grupo no DB: {e}")
            grupos[grupo].remove(user_add)  # Reverte
            conn.sendall("ERRO|Falha interna no servidor.".encode('utf-8'))


def lista_membros(partes, conn):
    grupo = partes[1]
    if grupo in grupos:
        membros = ", ".join(grupos[grupo])
        conn.sendall(f"INFO|Membros do grupo {grupo}: {membros}".encode('utf--8'))
    else:
        conn.sendall("ERRO|Grupo não existe.".encode('utf-8'))


def sair_grupo(partes, username, conn):
    grupo = partes[1]
    with lock:
        if grupo in grupos and username in grupos[grupo]:
            grupos[grupo].remove(username)

            # [DB] Atualiza no MongoDB
            try:
                grupos_collection.update_one(
                    {'nome': grupo},
                    {'$pull': {'membros': username}}
                )
                conn.sendall(f"INFO|Você saiu do grupo {grupo}".encode('utf-8'))
            except Exception as e:
                print(f"[ERRO DB] Falha ao sair do grupo no DB: {e}")
                grupos[grupo].append(username)  # Reverte


def apagar_grupo(partes, username, conn):
    grupo = partes[1]
    with lock:
        if grupo in grupos and username in grupos[grupo]:
            del grupos[grupo]
            try:
                grupos_collection.delete_one({'nome': grupo})
                broadcast(f"INFO|Grupo {grupo} apagado por {username}")
            except Exception as e:
                print(f"[ERRO DB] Falha ao apagar grupo no DB: {e}")
        else:
            conn.sendall("ERRO|Você não pode apagar esse grupo.".encode('utf-8'))


def listar_usuarios_e_grupos(conn):
    with lock:
        usuarios = "Usuários conectados: " + (", ".join(clientes.keys()) if clientes else "Nenhum")
        grupos_list = "Grupos existentes: " + (", ".join(grupos.keys()) if grupos else "Nenhum")

    conn.sendall(f"INFO|{usuarios}".encode('utf-8'))
    # CORREÇÃO: A linha abaixo estava faltando o "INFO|" no início.
    conn.sendall(f"INFO|{grupos_list}".encode('utf-8'))


def enviar_arquivo(partes, username, conn):
    try:
        destino, nome_arquivo, tamanho = partes[1], partes[2], int(partes[3])
        conn.sendall("OK_ARQUIVO".encode('utf-8'))
        bytes_recebidos = 0
        destinatarios = []
        if destino in clientes:
            destinatarios = [clientes[destino]]
        elif destino in grupos:
            destinatarios = [clientes[m] for m in grupos[destino] if m != username and m in clientes]
        for sock_dest in destinatarios:
            sock_dest.sendall(f"FILE_TRANSFER|{username}|{nome_arquivo}|{tamanho}".encode('utf-8'))
        while bytes_recebidos < tamanho:
            to_read = min(4096, tamanho - bytes_recebidos)
            pacote = conn.recv(to_read)
            if not pacote: raise ConnectionError("Conexão encerrada")
            bytes_recebidos += len(pacote)
            for sock_dest in destinatarios:
                sock_dest.sendall(pacote)
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
            conn.close()
            return None


def handle_acoes(username, conn):
    while True:
        try:
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
                    apagar_grupo(partes, username, conn)
                case "LISTAR":
                    listar_usuarios_e_grupos(conn)
                case "SAIR":
                    break
                case "ARQUIVO":
                    enviar_arquivo(partes, username, conn)
                case _:
                    print(f"[WARN] comando desconhecido de {username}: {comando}")
        except ConnectionResetError:
            break
        except Exception as e:
            print(f"[ERRO] Exceção no loop de ações para {username}: {e}")
            break


# --- Lógica Cliente ---
def gerenciar_cliente(conn, addr):
    username = handle_usuario(addr, conn)
    if username:
        print(f"[NOVA CONEXÃO] {username} ({addr}) conectado.")
        print(f"[SERVIDOR] {len(clientes)} clientes conectados, {len(grupos)} grupos criados")

        # --- NOVIDADE: Envia uma mensagem a todos informando do novo usuário ---
        mensagem_entrada = f"INFO|{username} entrou no chat."
        broadcast(mensagem_entrada, ignorar=username)  # Envia para todos, exceto para quem acabou de entrar

        try:
            handle_acoes(username, conn)
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

    carregar_dados_do_db()

    while True:
        conn, addr = servidor.accept()
        threading.Thread(target=gerenciar_cliente, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    iniciar_servidor()