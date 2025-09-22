# cliente.py (versão ajustada para shutdown/threads seguros)
import socket
import threading
import os
import time

file_transfer_in_progress = threading.Event()
stop_event = threading.Event()

def menu_acoes():
    print("\n--- Comandos ---")
    print("  msg <usuario|grupo> <mensagem>             - Enviar mensagem")
    print("  criar <grupo>                              - Criar grupo")
    print("  entrar <grupo>                             - Entrar em grupo")
    print("  add <usuario> <grupo>                      - Adicionar usuário em grupo")
    print("  membros <grupo>                            - Listar membros de grupo")
    print("  sairgrupo <grupo>                          - Sair de grupo")
    print("  apagargrupo <grupo>                        - Apagar grupo")
    print("  arquivo <destino> \"<caminho arquivo>\"*   - Enviar arquivo")
    print("  listar                                     - Listar usuários e grupos")
    print("  sair                                       - Desconectar")
    print("  help                                       - Menu de ações\n")
    print("\n* Use aspas se o caminho tiver espaços \n")

def receber_mensagens(cliente_socket):
    """ Recebe mensagens do servidor em loop """
    try:
        while not stop_event.is_set():
            try:
                if file_transfer_in_progress.is_set():
                    time.sleep(0.1)
                    continue

                cliente_socket.settimeout(1.0)
                try:
                    msg = cliente_socket.recv(4096)
                except socket.timeout:
                    continue
                finally:
                    cliente_socket.settimeout(None)

                if not msg:
                    print("\n[CONEXÃO] Conexão com o servidor perdida.")
                    break

                mensagem = msg.decode('utf-8', errors='ignore')
                partes = mensagem.split('|')
                tipo = partes[0]

                if tipo == "FILE_TRANSFER":
                    _, remetente, nome_arquivo, tamanho_str = partes
                    tamanho_arquivo = int(tamanho_str)
                    print(f"\n[INFO] Recebendo arquivo '{nome_arquivo}' de {remetente} ({tamanho_arquivo} bytes).")
                    receber_arquivo(cliente_socket, nome_arquivo, tamanho_arquivo)
                elif tipo == "MSG_PRIVADA":
                    remetente, conteudo = partes[1], '|'.join(partes[2:])
                    print(f"\n[Mensagem de {remetente}]: {conteudo}")
                elif tipo == "MSG_GRUPO":
                    grupo, remetente, conteudo = partes[1], partes[2], '|'.join(partes[3:])
                    print(f"\n[Grupo {grupo} | {remetente}]: {conteudo}")
                elif tipo in ["INFO", "ERRO"]:
                    print(f"\n[{tipo} Servidor]: {'|'.join(partes[1:])}")
                else:
                    print(f"\n{mensagem}")

            except (ConnectionResetError, OSError):
                # socket foi fechado/encerrado; fim do loop de recepção
                print("\n[CONEXÃO] Conexão encerrada pelo servidor ou socket fechado.")
                break
            except Exception as e:
                # Erro inesperado — imprime mensagem curta e encerra recepção
                print(f"\n[ERRO] Erro ao receber mensagem: {e}")
                break
    finally:
        # garante limpeza e sinaliza que a thread terminou
        stop_event.set()

def receber_arquivo(sock, nome_arquivo, tamanho_arquivo):
    """ Salva o arquivo recebido do servidor """
    try:
        if not os.path.exists('recebidos'):
            os.makedirs('recebidos')

        caminho_arquivo = os.path.join('recebidos', nome_arquivo)
        with open(caminho_arquivo, 'wb') as f:
            bytes_recebidos = 0
            while bytes_recebidos < tamanho_arquivo:
                bytes_a_receber = min(4096, tamanho_arquivo - bytes_recebidos)
                dados = sock.recv(bytes_a_receber)
                if not dados:
                    break
                f.write(dados)
                bytes_recebidos += len(dados)

        print(f"[INFO] Arquivo '{nome_arquivo}' salvo em 'recebidos/'.")
    except Exception as e:
        print(f"[ERRO] Falha ao receber o arquivo: {e}")

def enviar_arquivo_servidor(sock, destinatario, caminho_arquivo):
    """ Envia um arquivo para o servidor, com proteção contra shutdown """
    file_transfer_in_progress.set()
    try:
        nome_arquivo = os.path.basename(caminho_arquivo)
        tamanho_arquivo = os.path.getsize(caminho_arquivo)

        sock.sendall(f"ARQUIVO|{destinatario}|{nome_arquivo}|{tamanho_arquivo}".encode('utf-8'))

        sock.settimeout(5.0)
        resposta_inicial = sock.recv(1024).decode('utf-8')
        sock.settimeout(None)

        if resposta_inicial.startswith("OK_ARQUIVO"):
            with open(caminho_arquivo, 'rb') as f:
                bytes_enviados = 0
                while bytes_enviados < tamanho_arquivo and not stop_event.is_set():
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    bytes_enviados += len(chunk)

            sock.settimeout(10.0)
            try:
                resposta_final = sock.recv(1024).decode('utf-8')
            except socket.timeout:
                resposta_final = ""
            sock.settimeout(None)

            if resposta_final == "ARQUIVO_OK":
                print(f"[INFO] Arquivo '{nome_arquivo}' enviado com sucesso.")
            else:
                print(f"[ERRO] Resposta inesperada do servidor após envio: {resposta_final}")
        else:
            print(f"[ERRO] Servidor recusou envio. Resposta: {resposta_inicial}")

    except socket.timeout:
        print("[ERRO] Tempo de espera esgotado. O servidor não respondeu.")
    except (OSError, ConnectionResetError) as e:
        print(f"[ERRO] Falha ao enviar o arquivo (socket): {e}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar o arquivo: {e}")
    finally:
        file_transfer_in_progress.clear()

def create_usuario(cliente):
    while not stop_event.is_set():
        username = input("Digite seu nome de usuário: ")
        try:
            cliente.sendall(username.encode('utf-8'))
            resposta = cliente.recv(1024).decode('utf-8')
        except Exception as e:
            print(f"[ERRO] Falha na comunicação ao definir usuário: {e}")
            return None
        if resposta == "NOME_OK":
            return username
        else:
            print(f"{resposta}")
    return None

def switch_acoes(comando, partes, cliente):
    match comando:
        case "arquivo" if len(partes) >= 3:
            caminho_arquivo = partes[2]
            if caminho_arquivo.startswith('"') and caminho_arquivo.endswith('"'):
                caminho_arquivo = caminho_arquivo[1:-1]
            if os.path.exists(caminho_arquivo):
                enviar_arquivo_servidor(cliente, partes[1], caminho_arquivo)
            else:
                print(f"[ERRO] Arquivo '{caminho_arquivo}' não encontrado.")
        case "arquivo":
            pass
        case "msg" if len(partes) == 3:
            cliente.sendall(f"MSG|{partes[1]}|{partes[2]}".encode('utf-8'))
        case "criar" if len(partes) == 2:
            cliente.sendall(f"CRIAR_GRUPO|{partes[1]}".encode('utf-8'))
        case "entrar" if len(partes) == 2:
            cliente.sendall(f"ENTRAR_GRUPO|{partes[1]}".encode('utf-8'))
        case "add" if len(partes) == 3:
            cliente.sendall(f"ADD_GRUPO|{partes[1]}|{partes[2]}".encode('utf-8'))
        case "membros" if len(partes) == 2:
            cliente.sendall(f"MEMBROS|{partes[1]}".encode('utf-8'))
        case "sairgrupo" if len(partes) == 2:
            cliente.sendall(f"SAIR_GRUPO|{partes[1]}".encode('utf-8'))
        case "apagargrupo" if len(partes) == 2:
            cliente.sendall(f"APAGAR_GRUPO|{partes[1]}".encode('utf-8'))
        case "listar":
            cliente.sendall("LISTAR|".encode('utf-8'))
        case "sair":
            try:
                cliente.sendall("SAIR|".encode('utf-8'))
            except Exception:
                pass
            return "break"
        case "help":
            menu_acoes()
        case _:
            if comando != "arquivo":
                print("[ERRO] Comando inválido ou formato incorreto.")

def handle_acoes(username, cliente):
    while not stop_event.is_set():
        entrada = input(f"[{username}]> ").strip()
        if not entrada:
            continue
        partes = entrada.split(' ', 2)
        comando = partes[0].lower()
        try:
            acao = switch_acoes(comando, partes, cliente)
            if acao == "break":
                break
        except Exception as e:
            print(f"[ERRO] {e}")
            break

def iniciar_cliente():
    HOST = '192.168.6.237'
    PORT = 65432

    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente.connect((HOST, PORT))
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar: {e}")
        return

    username = create_usuario(cliente)
    if not username:
        cliente.close()
        return

    # Cria thread de recepção e guarda referência para join
    receiver_thread = threading.Thread(target=receber_mensagens, args=(cliente,))
    receiver_thread.start()

    menu_acoes()
    try:
        handle_acoes(username, cliente)
    finally:
        # Fluxo de saída ordenado
        stop_event.set()
        # garante que não estamos travados em operações de socket
        try:
            cliente.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            cliente.close()
        except Exception:
            pass

        # aguarda a thread de recebimento terminar (timeout opcional)
        receiver_thread.join(timeout=3.0)
        print("[INFO] Cliente finalizado.")

if __name__ == "__main__":
    iniciar_cliente()
