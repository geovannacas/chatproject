# cliente.py
import socket
import threading
import os

# --- Funções do Cliente ---

def receber_mensagens(cliente_socket):
    """ Recebe mensagens do servidor em loop """
    while True:
        try:
            mensagem = cliente_socket.recv(4096).decode('utf-8')
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

            elif tipo in ["INFO", "ERRO"]:
                print(f"\n[{tipo} Servidor]: {'|'.join(partes[1:])}")

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
    """ Salva o arquivo recebido do servidor """
    try:
        if not os.path.exists('recebidos'):
            os.makedirs('recebidos')

        caminho_arquivo = os.path.join('recebidos', nome_arquivo)

        bytes_recebidos = 0
        with open(caminho_arquivo, 'wb') as f:
            while bytes_recebidos < tamanho_arquivo:
                dados = sock.recv(min(4096, tamanho_arquivo - bytes_recebidos))
                if not dados:
                    break
                f.write(dados)
                bytes_recebidos += len(dados)

        print(f"[INFO] Arquivo '{nome_arquivo}' salvo em 'recebidos/'.")
    except Exception as e:
        print(f"[ERRO] Falha ao receber o arquivo: {e}")


def iniciar_cliente():
    """ Conecta ao servidor e gerencia comandos do usuário """
    HOST = '10.1.5.60'
    PORT = 65432

    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente.connect((HOST, PORT))
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar: {e}")
        return


    while True:
        username = input("Digite seu nome de usuário: ")
        cliente.sendall(username.encode('utf-8'))
        resposta = cliente.recv(1024).decode('utf-8')

        if resposta == "NOME_OK":
            # print(f"[INFO] Nome '{username}' aceito. Bem-vindo!")
            break
        else:
            print(f"{resposta}")  # mensagem de erro vem do servidor

    # Thread para ficar ouvindo mensagens
    threading.Thread(target=receber_mensagens, args=(cliente,), daemon=True).start()

    print("\n--- Comandos ---")
    print("  msg <usuario|grupo> <mensagem>  - Enviar mensagem")
    print("  criar <grupo>                  - Criar grupo")
    print("  entrar <grupo>                 - Entrar em grupo")
    print("  add <usuario> <grupo>          - Adicionar usuário em grupo")
    print("  membros <grupo>                - Listar membros de grupo")
    print("  sairgrupo <grupo>              - Sair de grupo")
    print("  apagargrupo <grupo>            - Apagar grupo")
    print("  arquivo <destino> <arquivo>    - Enviar arquivo")
    print("  listar                         - Listar usuários e grupos")
    print("  sair                           - Desconectar\n")

    while True:
        entrada = input(f"[{username}]> ").strip()
        if not entrada:
            continue

        partes = entrada.split(' ', 2)
        comando = partes[0].lower()

        try:
            if comando == "msg" and len(partes) == 3:
                cliente.sendall(f"MSG|{partes[1]}|{partes[2]}".encode('utf-8'))

            elif comando == "criar" and len(partes) == 2:
                cliente.sendall(f"CRIAR_GRUPO|{partes[1]}".encode('utf-8'))

            elif comando == "entrar" and len(partes) == 2:
                cliente.sendall(f"ENTRAR_GRUPO|{partes[1]}".encode('utf-8'))

            elif comando == "add" and len(partes) == 3:
                cliente.sendall(f"ADD_GRUPO|{partes[1]}|{partes[2]}".encode('utf-8'))

            elif comando == "membros" and len(partes) == 2:
                cliente.sendall(f"MEMBROS|{partes[1]}".encode('utf-8'))

            elif comando == "sairgrupo" and len(partes) == 2:
                cliente.sendall(f"SAIR_GRUPO|{partes[1]}".encode('utf-8'))

            elif comando == "apagargrupo" and len(partes) == 2:
                cliente.sendall(f"APAGAR_GRUPO|{partes[1]}".encode('utf-8'))

            elif comando == "arquivo" and len(partes) == 3:
                if os.path.exists(partes[2]):
                    enviar_arquivo_servidor(cliente, partes[1], partes[2])
                else:
                    print(f"[ERRO] Arquivo '{partes[2]}' não encontrado.")

            elif comando == "listar":
                cliente.sendall("LISTAR|".encode('utf-8'))

            elif comando == "sair":
                cliente.sendall("SAIR|".encode('utf-8'))
                break

            else:
                print("[ERRO] Comando inválido.")

        except Exception as e:
            print(f"[ERRO] {e}")
            break

    cliente.close()


def enviar_arquivo_servidor(sock, destinatario, caminho_arquivo):
    """ Envia um arquivo para o servidor """
    try:
        nome_arquivo = os.path.basename(caminho_arquivo)
        tamanho_arquivo = os.path.getsize(caminho_arquivo)

        sock.sendall(f"ARQUIVO|{destinatario}|{nome_arquivo}|{tamanho_arquivo}".encode('utf-8'))

        if sock.recv(1024).decode('utf-8') == "OK_ARQUIVO":
            with open(caminho_arquivo, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sock.sendall(chunk)

            # Espera 5 segundos a resposta final do servidor
            sock.settimeout(5)
            resposta_final = sock.recv(1024).decode('utf-8')
            sock.settimeout(None)

            if resposta_final == "ARQUIVO_OK":
                print(f"[INFO] Arquivo '{nome_arquivo}' enviado com sucesso.")
            else:
                print(f"[ERRO] {resposta_final}")
        else:
            print("[ERRO] Servidor recusou envio.")

    except Exception as e:
        print(f"[ERRO] {e}")


if __name__ == "__main__":
    iniciar_cliente()
