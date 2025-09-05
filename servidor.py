import socket

# Define o endereço IP do host e a porta
# '127.0.0.1' é o endereço de loopback (localhost), ou seja, sua própria máquina.
HOST = '127.0.0.1'
PORT = 65432  # Porta acima de 1023 para não exigir privilégio de administrador

# socket.socket() cria um objeto socket.
# AF_INET especifica que usaremos o protocolo IPv4.
# SOCK_STREAM especifica que usaremos o protocolo TCP.
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # s.bind() associa o socket a um endereço IP e porta específicos.
    s.bind((HOST, PORT))

    # s.listen() coloca o socket em modo de escuta, aguardando conexões de clientes.
    s.listen()
    print(f"Servidor ouvindo em {HOST}:{PORT}")

    # s.accept() bloqueia a execução e espera por uma conexão.
    # Quando um cliente se conecta, ele retorna um novo objeto de socket (conn)
    # e o endereço do cliente (addr).
    conn, addr = s.accept()
    with conn:
        print(f"Conectado por {addr}")

        # Loop para receber dados do cliente
        while True:
            # conn.recv(1024) lê os dados recebidos do cliente.
            # 1024 é o tamanho do buffer em bytes.
            data = conn.recv(1024)

            # Se recv() retornar um objeto de bytes vazio, o cliente fechou a conexão.
            if not data:
                break

            # A mensagem chega como bytes, então a decodificamos para string.
            mensagem_cliente = data.decode('utf-8')
            print(f"Cliente: {mensagem_cliente}")

            # conn.sendall() envia uma resposta de volta para o cliente.
            # A mensagem deve ser codificada para bytes.
            conn.sendall(b'Mensagem recebida pelo servidor!')