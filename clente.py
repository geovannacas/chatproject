# cliente.py
import socket
import threading
import os


# --- Funções do Cliente ---

def receber_mensagens(cliente_socket):
    """ Lida com o recebimento de mensagens do servidor. """
    while True:
        try:
            mensagem = cliente_socket.recv(1024).decode('utf-8')
            if not mensagem:
                print("[CONEXÃO] Conexão com o servidor perdida.")
                break

            partes = mensagem.split('|')
            tipo = partes[0]

            if tipo == "MSG_PRIVADA":
                remetente, conteudo = partes[1], '|'.join(partes[2:])
                print(f"\n[Mensagem de {remetente}]: {conteudo}")
            elif tipo == "MSG_GRUPO":
                grupo, remetente, conteudo = partes[1], partes[2], '|'.join(partes[3:])
                print(f"\n[Grupo {grupo} | {remetente}]: {conteudo}")
            elif tipo == "INFO" or tipo == "ERRO":
                print(f"\n[{tipo} do Servidor]: {'|'.join(partes[1:])}")
            elif tipo == "FILE_TRANSFER":
                _, remetente, nome_arquivo, tamanho_str = partes
                tamanho_arquivo = int(tamanho_str)
                print(f"\n[INFO] Recebendo arquivo '{nome_arquivo}' de {remetente} ({tamanho_arquivo} bytes).")
                receber_arquivo(cliente_socket, nome_arquivo, tamanho_arquivo)
            else:
                print(f"\n{mensagem}")

        except Exception as e:
            print(f"[ERRO] Erro ao receber mensagem: {e}")
            break


def receber_arquivo(sock, nome_arquivo, tamanho_arquivo):
    """ Recebe um arquivo do servidor. """
    try:
        # Garante que o diretório 'recebidos' exista
        if not os.path.exists('recebidos'):
            os.makedirs('recebidos')

        caminho_arquivo = os.path.join('recebidos', nome_arquivo)

        bytes_recebidos = 0
        with open(caminho_arquivo, 'wb') as f:
            while bytes_recebidos < tamanho_arquivo:
                bytes_para_ler = min(4096, tamanho_arquivo - bytes_recebidos)
                dados = sock.recv(bytes_para_ler)
                if not dados:
                    break
                f.write(dados)
                bytes_recebidos += len(dados)
        print(f"[INFO] Arquivo '{nome_arquivo}' recebido com sucesso e salvo em 'recebidos/'.")
    except Exception as e:
        print(f"[ERRO] Falha ao receber o arquivo: {e}")


def iniciar_cliente():
    """ Inicia o cliente e conecta ao servidor. """
    HOST = input("Digite o IP do servidor (padrão 127.0.0.1): ") or '192.168.5.185'
    PORT = 65432

    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente.connect((HOST, PORT))
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao servidor: {e}")
        return

    username = input("Digite seu nome de usuário: ")
    cliente.sendall(username.encode('utf-8'))

    # Inicia uma thread para receber mensagens
    thread_recebimento = threading.Thread(target=receber_mensagens, args=(cliente,))
    thread_recebimento.daemon = True
    thread_recebimento.start()

    print("\n--- Comandos Disponíveis ---")
    print("  msg <usuario> <mensagem>     - Enviar mensagem privada")
    print("  msg <grupo> <mensagem>       - Enviar mensagem para um grupo")
    print("  criar <nome_do_grupo>        - Criar um novo grupo")
    print("  entrar <nome_do_grupo>       - Entrar em um grupo existente")
    print("  arquivo <usuario_ou_grupo> <caminho_do_arquivo> - Enviar um arquivo")
    print("  listar                       - Listar usuários e grupos")
    print("  sair                         - Desconectar do chat")
    print("----------------------------\n")

    while True:
        entrada = input(f"[{username}]> ")
        if not entrada:
            continue

        partes = entrada.split(' ', 2)
        comando = partes[0].lower()

        try:
            if comando == "msg" and len(partes) == 3:
                destinatario, conteudo = partes[1], partes[2]
                cliente.sendall(f"MSG|{destinatario}|{conteudo}".encode('utf-8'))

            elif comando == "criar" and len(partes) == 2:
                nome_grupo = partes[1]
                cliente.sendall(f"CRIAR_GRUPO|{nome_grupo}".encode('utf-8'))

            elif comando == "entrar" and len(partes) == 2:
                nome_grupo = partes[1]
                cliente.sendall(f"ENTRAR_GRUPO|{nome_grupo}".encode('utf-8'))

            elif comando == "arquivo" and len(partes) == 3:
                destinatario, caminho_arquivo = partes[1], partes[2]
                if os.path.exists(caminho_arquivo):
                    enviar_arquivo_servidor(cliente, destinatario, caminho_arquivo)
                else:
                    print(f"[ERRO] Arquivo local '{caminho_arquivo}' não encontrado.")

            elif comando == "listar":
                cliente.sendall("LISTAR|".encode('utf-8'))

            elif comando == "sair":
                cliente.sendall("SAIR|".encode('utf-8'))
                break

            else:
                print("[ERRO] Comando inválido ou formato incorreto.")

        except IndexError:
            print("[ERRO] Formato de comando incorreto. Verifique os parâmetros.")
        except Exception as e:
            print(f"[ERRO] Ocorreu um erro: {e}")
            break

    cliente.close()


def enviar_arquivo_servidor(sock, destinatario, caminho_arquivo):
    """ Solicita ao servidor o envio de um arquivo. """
    try:
        nome_arquivo = os.path.basename(caminho_arquivo)
        tamanho_arquivo = os.path.getsize(caminho_arquivo)

        # Envia metadados para o servidor
        sock.sendall(f"ARQUIVO|{destinatario}|{nome_arquivo}|{tamanho_arquivo}".encode('utf-8'))

        # Aguarda confirmação do servidor antes de enviar o conteúdo
        resposta = sock.recv(1024).decode('utf-8')
        if resposta == "OK_ARQUIVO":
            with open(caminho_arquivo, 'rb') as f:
                while True:
                    bytes_lidos = f.read(4096)
                    if not bytes_lidos:
                        break
                    sock.sendall(bytes_lidos)
            print(f"[INFO] Arquivo '{nome_arquivo}' enviado para o servidor.")
        else:
            print(f"[ERRO do Servidor] {resposta}")

    except FileNotFoundError:
        print(f"[ERRO] Arquivo '{caminho_arquivo}' não encontrado.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar o arquivo: {e}")


if __name__ == "__main__":
    iniciar_cliente()