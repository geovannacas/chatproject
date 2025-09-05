import socket

# As mesmas configurações de host e porta do servidor
HOST = '127.0.0.1'
PORT = 65432

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # s.connect() conecta o socket ao endereço e porta do servidor.
    s.connect((HOST, PORT))

    # A mensagem a ser enviada deve ser codificada para bytes.
    mensagem = "Ola, servidor!"
    s.sendall(mensagem.encode('utf-8'))

    # s.recv(1024) aguarda e recebe a resposta do servidor.
    data = s.recv(1024)

    # A resposta do servidor (em bytes) é decodificada para string.
    print(f"Servidor: {data.decode('utf-8')}")