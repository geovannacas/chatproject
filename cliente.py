# cliente.py
import socket       # Biblioteca padrão para comunicação de rede (sockets)
import threading    # Módulo para gerenciar threads (execução de tarefas em paralelo)
import os           # Módulo para interagir com o sistema operacional (caminhos de arquivo, etc.)
import time         # Módulo para funções relacionadas ao tempo

# Cria um objeto Event. Ele funciona como uma "bandeira" que pode ser levantada (set) ou abaixada (clear)
# É útil para sincronização entre threads, avisando uma thread que algo aconteceu
file_transfer_in_progress = threading.Event()


def receber_mensagens(cliente_socket):
    """ Recebe mensagens do servidor em loop """
    while True:
        try:
            # Verifica se a "bandeira" da transferência está levantada (set) se is_set for true
            # uma transferência de arquivo está em andamento
            if file_transfer_in_progress.is_set():
                time.sleep(0.1)     # Se estiver, espera um pouco e tenta de novo
                continue            # de recebimento de mensagens tente ler o socket ao mesmo tempo que a de envio de arquivo

            # Se a bandeira não está levantada,  ler mensagens normalmente
            cliente_socket.settimeout(1.0)
            # timeout no socket para não ficar bloqueado para sempre aqui
            # Isso permite que o loop continue e verifique o Event novamente
            try:
                 # Tenta receber 4096 bytes do socket. O timeout garante que essa chamada
                 # não trava a thread para sempre
                mensagem = cliente_socket.recv(4096).decode('utf-8', errors='ignore')
            except socket.timeout:
                continue  # Nenhuma mensagem, apenas volta ao início do loop para re-checar a bandeira
            finally:
                # Remove o timeout para que o socket volte ao comportamento padrão de bloqueio
                cliente_socket.settimeout(None)  # Remove o timeout

            if not mensagem:
                # Se a mensagem estiver vazia, significa que a conexão foi encerrada pelo servidor
                print("\n[CONEXÃO] Conexão com o servidor perdida.")
                break

            # Lógica para processar a mensagem recebida
            partes = mensagem.split('|')
            tipo = partes[0]

            if tipo == "FILE_TRANSFER":
                _, remetente, nome_arquivo, tamanho_str = partes
                tamanho_arquivo = int(tamanho_str)
                print(f"\n[INFO] Recebendo arquivo '{nome_arquivo}' de {remetente} ({tamanho_arquivo} bytes).")
                # Chama a função receber_arquivo para lidar com o recebimento do arquivo
                receber_arquivo(cliente_socket, nome_arquivo, tamanho_arquivo)
            elif tipo == "MSG_PRIVADA":
                # mensagem privada
                remetente, conteudo = partes[1], '|'.join(partes[2:])
                print(f"\n[Mensagem de {remetente}]: {conteudo}")
            elif tipo == "MSG_GRUPO":
                # mensagem em grupo
                grupo, remetente, conteudo = partes[1], partes[2], '|'.join(partes[3:])
                print(f"\n[Grupo {grupo} | {remetente}]: {conteudo}")
            elif tipo in ["INFO", "ERRO"]:
                # mensagens de informação ou erro do servidor
                print(f"\n[{tipo} Servidor]: {'|'.join(partes[1:])}")
            elif mensagem:
                print(f"\n{mensagem}")

        except ConnectionResetError:
            print("\n[CONEXÃO] Conexão com o servidor foi perdida.")
            break
        except Exception as e:
            print(f"\n[ERRO] Erro ao receber mensagem: {e}")
            break


def receber_arquivo(sock, nome_arquivo, tamanho_arquivo):
    """ Salva o arquivo recebido do servidor """
    try:
        # Cria a pasta 'recebidos' se ela não existir
        if not os.path.exists('recebidos'):
            os.makedirs('recebidos')

        caminho_arquivo = os.path.join('recebidos', nome_arquivo)

        # Abre o arquivo em modo de escrita binária ('wb') para salvar os dados
        with open(caminho_arquivo, 'wb') as f:
            bytes_recebidos = 0
            # Loop para receber todos os bytes do arquivo
            while bytes_recebidos < tamanho_arquivo:
                 # Recebe dados em pedaços de 4096 bytes ou o que falta para completar
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
    """ Envia um arquivo para o servidor """
    # Seta o Event para True, sinalizando que a transferência está ocorrendo
    file_transfer_in_progress.set()
    try:
        # Pega o nome e o tamanho do arquivo
        nome_arquivo = os.path.basename(caminho_arquivo)
        tamanho_arquivo = os.path.getsize(caminho_arquivo)

        # Envia a metainformação do arquivo para o servido
        sock.sendall(f"ARQUIVO|{destinatario}|{nome_arquivo}|{tamanho_arquivo}".encode('utf-8'))

        # O timeout aqui é importante para não travar o programa se o servidor não responder
        sock.settimeout(5.0)
        resposta_inicial = sock.recv(1024).decode('utf-8')
        sock.settimeout(None)

        if resposta_inicial.startswith("OK_ARQUIVO"):
            # Se o servidor estiver pronto, abre o arquivo para leitura binária
            with open(caminho_arquivo, 'rb') as f:
                bytes_enviados = 0
                 # Envia o arquivo em pedaços
                while bytes_enviados < tamanho_arquivo:
                    chunk = f.read(4096)
                    if not chunk: break
                    sock.sendall(chunk)
                    bytes_enviados += len(chunk)

            sock.settimeout(10.0)  # Timeout maior para a confirmação final
            resposta_final = sock.recv(1024).decode('utf-8')
            sock.settimeout(None)

            if resposta_final == "ARQUIVO_OK":
                print(f"[INFO] Arquivo '{nome_arquivo}' enviado com sucesso.")
            else:
                print(f"[ERRO] Resposta inesperada do servidor após envio: {resposta_final}")
        else:
            print(f"[ERRO] Servidor recusou envio. Resposta: {resposta_inicial}")

    except socket.timeout:
        print("[ERRO] Tempo de espera esgotado. O servidor não respondeu.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar o arquivo: {e}")
    finally:
        # Limpa o Event (seta para False), permitindo que a thread de recebimento
        # de mensagens volte a funcionar normalmente
        file_transfer_in_progress.clear()


def iniciar_cliente():
    """ Conecta ao servidor e gerencia comandos do usuário """
    HOST = '10.1.5.60'   # Lembre-se de usar o IP correto do servidor. Como saber? ipconfig no bash
    PORT = 65432            # Tem que ser a mesma porta do servidor

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
            break
        else:
            print(f"{resposta}")

    # Cria e inicia uma nova thread para receber mensagens do servidor em segundo plano
    # O 'daemon=True' garante que a thread será encerrada quando o programa principal terminar
    threading.Thread(target=receber_mensagens, args=(cliente,), daemon=True).start()

    print("\n--- Comandos ---")
    # ... (o print dos comandos continua o mesmo)
    print("  msg <usuario|grupo> <mensagem>             - Enviar mensagem")
    print("  criar <grupo>                              - Criar grupo")
    print("  entrar <grupo>                             - Entrar em grupo")
    print("  add <usuario> <grupo>                      - Adicionar usuário em grupo")
    print("  membros <grupo>                            - Listar membros de grupo")
    print("  sairgrupo <grupo>                          - Sair de grupo")
    print("  apagargrupo <grupo>                        - Apagar grupo")
    print("  arquivo <destino> \"<caminho arquivo>\"*   - Enviar arquivo")
    print("  listar                                     - Listar usuários e grupos")
    print("  sair                                       - Desconectar\n")
    print("\n* Use aspas se o caminho tiver espaços \n")

    while True:
        # Loop principal para ler comandos do usuário e enviá-los ao servidor
        entrada = input(f"[{username}]> ").strip()
        if not entrada: continue

        partes = entrada.split(' ', 2)
        comando = partes[0].lower()

        try:
            if comando == "arquivo" and len(partes) >= 3:
                # Lida com o comando de envio de arquivo
                caminho_arquivo = partes[2]
                if caminho_arquivo.startswith('"') and caminho_arquivo.endswith('"'):
                    caminho_arquivo = caminho_arquivo[1:-1]

                if os.path.exists(caminho_arquivo):
                    enviar_arquivo_servidor(cliente, partes[1], caminho_arquivo)
                else:
                    print(f"[ERRO] Arquivo '{caminho_arquivo}' não encontrado.")
            elif comando == "msg" and len(partes) == 3:
                # Envia uma mensagem para um usuário ou grupo
                cliente.sendall(f"MSG|{partes[1]}|{partes[2]}".encode('utf-8'))
            elif comando == "criar" and len(partes) == 2:
                # Envia um comando para criar um grupo
                cliente.sendall(f"CRIAR_GRUPO|{partes[1]}".encode('utf-8'))
            elif comando == "entrar" and len(partes) == 2:
                # Envia um comando para entrar em um grupo
                cliente.sendall(f"ENTRAR_GRUPO|{partes[1]}".encode('utf-8'))
            elif comando == "add" and len(partes) == 3:
                # Envia um comando para adicionar um usuário em um grupo
                cliente.sendall(f"ADD_GRUPO|{partes[1]}|{partes[2]}".encode('utf-8'))
            elif comando == "membros" and len(partes) == 2:
                # Envia um comando para listar os membros de um grupo
                cliente.sendall(f"MEMBROS|{partes[1]}".encode('utf-8'))
            elif comando == "sairgrupo" and len(partes) == 2:
                # Envia um comando para sair de um grupo
                cliente.sendall(f"SAIR_GRUPO|{partes[1]}".encode('utf-8'))
            elif comando == "apagargrupo" and len(partes) == 2:
                # Envia um comando para apagar um grupo
                cliente.sendall(f"APAGAR_GRUPO|{partes[1]}".encode('utf-8'))
            elif comando == "listar":
                # Envia um comando para listar usuários e grupos
                cliente.sendall("LISTAR|".encode('utf-8'))
            elif comando == "sair":
                # Envia um comando para sair do chat
                cliente.sendall("SAIR|".encode('utf-8'))
                break
            elif comando != "arquivo":
                print("[ERRO] Comando inválido ou formato incorreto.")
        except Exception as e:
            print(f"[ERRO] {e}")
            break
    cliente.close()


if __name__ == "__main__":
    iniciar_cliente()
