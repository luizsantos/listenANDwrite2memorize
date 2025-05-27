import os
import subprocess
import random # Para aleatoriedade

import sys # Para acessar argumentos da linha de comando
# --- Configurações do Piper ---
# Ajuste estes caminhos conforme a sua instalação
CAMINHO_EXECUTAVEL_PIPER = "./piper/piper"  # Ex: /home/seu_usuario/piper/piper ou ./piper/piper se estiver na mesma pasta
CAMINHO_MODELO_VOZ_ONNX = "./piper_voices/en_US-hfc_female-medium.onnx" # Ex: /home/seu_usuario/vozes_piper/en_US-lessac-medium.onnx
# O arquivo .onnx.json deve estar na mesma pasta que o .onnx e ter o mesmo nome base.

# --- Constantes do Jogo ---
MASTERY_THRESHOLD = 2 # Número de acertos para considerar uma palavra masterizada

def verificar_piper():
    """Verifica se o executável do Piper e o modelo de voz existem."""
    if not os.path.exists(CAMINHO_EXECUTAVEL_PIPER):
        print(f"Erro: Executável do Piper não encontrado em '{CAMINHO_EXECUTAVEL_PIPER}'")
        print("Faça o download em https://github.com/rhasspy/piper/releases")
        return False
    if not os.path.exists(CAMINHO_MODELO_VOZ_ONNX):
        print(f"Erro: Modelo de voz ONNX do Piper não encontrado em '{CAMINHO_MODELO_VOZ_ONNX}'")
        print("Faça o download de um modelo de voz em inglês (ex: en_US-lessac-medium.onnx e .json).")
        return False
    return True

def falar_palavra_piper(palavra, length_scale=1.0):
    """Usa o Piper para falar a palavra em inglês."""
    if not verificar_piper():
        return False

    # O Piper gera um arquivo .wav. Vamos chamá-lo de 'output.wav' e depois tocá-lo.
    arquivo_saida_wav = "output.wav"

    comando_piper = [
        CAMINHO_EXECUTAVEL_PIPER,
        "--model", CAMINHO_MODELO_VOZ_ONNX,
        "--output_file", arquivo_saida_wav,
        "--length_scale", str(length_scale) # Adiciona o argumento de velocidade
    ]
    # Piper lê o texto da entrada padrão (stdin)

    try:
        # Usamos Popen para poder enviar o texto para stdin
        process = subprocess.Popen(comando_piper, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Codifica a palavra para bytes e envia para o stdin do Piper
        stdout, stderr = process.communicate(input=palavra.encode('utf-8'))

        if process.returncode != 0:
            print(f"Erro ao executar o Piper: {stderr.decode('utf-8', errors='replace')}")
            return False

        # Verificar se o arquivo WAV foi realmente criado pelo Piper
        if not os.path.exists(arquivo_saida_wav):
            print(f"Erro: Piper indicou sucesso, mas o arquivo de áudio '{arquivo_saida_wav}' não foi encontrado.")
            if stdout:
                print(f"Saída padrão do Piper: {stdout.decode('utf-8', errors='replace')}")
            if stderr: # Mesmo que returncode seja 0, pode haver algo em stderr
                print(f"Saída de erro do Piper: {stderr.decode('utf-8', errors='replace')}")
            return False

        # Tocar o arquivo WAV gerado
        players = [
            {"name": "aplay", "path": "/usr/bin/aplay", "args": ["-q", arquivo_saida_wav]},
            {"name": "paplay", "path": "/usr/bin/paplay", "args": [arquivo_saida_wav]},
            # Você pode adicionar outros players aqui se desejar, ex: afplay para macOS
            # {"name": "afplay", "path": "/usr/bin/afplay", "args": [arquivo_saida_wav]},
        ]

        player_funcionou = False
        ultimo_erro_player = ""

        for player_info in players:
            player_executavel = player_info["path"]
            if os.path.exists(player_executavel):
                comando_player = [player_executavel] + player_info["args"]
                try:
                    # print(f"Tentando tocar com {player_info['name']}...") # Descomente para depuração
                    # Usamos capture_output=True para obter stdout/stderr do player
                    # Usamos check=False para não levantar exceção automaticamente em caso de erro
                    resultado_player = subprocess.run(comando_player, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)

                    if resultado_player.returncode == 0:
                        player_funcionou = True
                        break
                    else:
                        # Não imprimir o erro imediatamente, apenas armazenar para o caso de todos falharem.
                        # print(f"Falha ao usar {player_info['name']}. Código de saída: {resultado_player.returncode}") # Comentado
                        if resultado_player.stderr:
                            ultimo_erro_player = f"Erro do {player_info['name']} (código {resultado_player.returncode}): {resultado_player.stderr.strip()}"
                            # print(f"Erro do {player_info['name']}: {resultado_player.stderr.strip()}") # Comentado
                        elif resultado_player.stdout: # Alguns players podem enviar erros para stdout
                            ultimo_erro_player = f"Saída (possível erro) do {player_info['name']} (código {resultado_player.returncode}): {resultado_player.stdout.strip()}"
                            # print(f"Saída (possível erro) do {player_info['name']}: {resultado_player.stdout.strip()}") # Comentado
                        else:
                            ultimo_erro_player = f"Falha ao usar {player_info['name']} (código {resultado_player.returncode}) sem saída de erro detalhada."
                except FileNotFoundError: # Improvável se os.path.exists passou, mas por segurança
                    print(f"Erro: Executável do player {player_info['name']} não encontrado em '{player_executavel}'.")
                    ultimo_erro_player = f"Executável {player_info['name']} não encontrado."
                except Exception as e:
                    print(f"Erro inesperado ao tentar usar {player_info['name']}: {e}")
                    ultimo_erro_player = str(e)
        
        if not player_funcionou:
            print("\nErro: Nenhum player de áudio (aplay, paplay) conseguiu tocar o som.")
            if ultimo_erro_player:
                print(f"Detalhes da última tentativa de reprodução: {ultimo_erro_player}")
            
            print("\nSugestões para solução de problemas de áudio no Linux:")
            print("  1. Verifique se você tem 'alsa-utils' (para aplay) ou 'pulseaudio-utils' (para paplay) instalados.")
            print("     Ex: sudo apt install alsa-utils pulseaudio-utils")
            if "ALSA" in ultimo_erro_player or "unable to open slave" in ultimo_erro_player:
                print("  2. O erro parece relacionado ao ALSA. Certifique-se de que seu usuário pertence ao grupo 'audio'.")
                print("     Execute: sudo usermod -aG audio $USER")
                print("     Depois, saia da sessão e entre novamente, ou reinicie o computador.")
                print("  3. Verifique se nenhum outro aplicativo está usando o dispositivo de áudio exclusivamente.")
                print("  4. Se estiver usando PulseAudio ou PipeWire, garanta que estão funcionando corretamente.")
            return False

    except FileNotFoundError:
        print(f"Erro: O executável do Piper ('{CAMINHO_EXECUTAVEL_PIPER}') não foi encontrado.")
        return False
    finally:
        # Opcional: remover o arquivo .wav após tocar
        if os.path.exists(arquivo_saida_wav):
            try:
                os.remove(arquivo_saida_wav)
            except OSError as e:
                print(f"Aviso: Não foi possível remover o arquivo {arquivo_saida_wav}: {e}")
    return True


def selecionar_velocidade(opcoes_velocidade, escala_atual_valor):
    """Permite ao usuário selecionar uma velocidade de fala."""
    print("\nEscolha a velocidade da fala:")
    for key, info in opcoes_velocidade.items():
        atual_str = " (atual)" if info['scale'] == escala_atual_valor else ""
        print(f"  {key} - {info['nome']}{atual_str}")

    while True:
        prompt_msg = "Digite o número da opção desejada"
        if escala_atual_valor is not None: # Se estamos mudando, não na seleção inicial obrigatória
            prompt_msg += " (ou Enter para manter a atual): "
        else:
            prompt_msg += ": "
        
        escolha = input(prompt_msg).strip()
        if not escolha and escala_atual_valor is not None: # Usuário pressionou Enter e não é a seleção inicial
             print(f"Velocidade mantida: {next(v['nome'] for k, v in opcoes_velocidade.items() if v['scale'] == escala_atual_valor)}.")
             return escala_atual_valor
        if escolha in opcoes_velocidade:
            print(f"Velocidade '{opcoes_velocidade[escolha]['nome']}' selecionada.")
            return opcoes_velocidade[escolha]["scale"]
        else:
            print(f"Opção inválida. Por favor, digite um número entre 1 e {len(opcoes_velocidade)}.")

def gerar_dica(palavra_correta):
    """
    Gera uma dica para a palavra.
    Para palavras com mais de 2 caracteres, mostra a primeira e a última letra,
    com underscores no meio.
    Para palavras com 1 ou 2 caracteres, a dica é mais simples.
    """
    n = len(palavra_correta)
    if n == 0:
        return ""
    
    if n == 1: # Ex: "a" -> "a"
        return palavra_correta
    
    componentes_dica = []
    # Primeira letra
    componentes_dica.append(palavra_correta[0])
    
    # Underscores para as letras do meio (se houver)
    for _ in range(n - 2):
        componentes_dica.append("_")
    
    # Última letra (se a palavra tiver mais de uma letra)
    if n > 1: # Garante que não tentamos adicionar a última letra duas vezes para n=1
        componentes_dica.append(palavra_correta[-1])
        
    return " ".join(componentes_dica)

def exibir_trofeu():
    """Exibe uma arte ASCII de um troféu."""
    trofeu = [
        "      ___________      ",
        "     '._==_==_=_.'     ",
        "     .-\\:      /-.    ",
        "    | (|:.     |) |    ",
        "     '-|:.     |-'     ",
        "       \\::.    /      ",
        "        '::. .'        ",
        "          ) (          ",
        "        _.' '._        ",
        "       '-------'       "
    ]
    for linha in trofeu:
        print(linha)

def falar_frase_feedback(frase, velocidade_scale):
    """Usa o Piper para falar uma frase de feedback."""
    falar_palavra_piper(frase, velocidade_scale) # Reutiliza a função principal de fala

def exibir_estatisticas(palavras_estudo_final):
    """Exibe as estatísticas da sessão de estudo."""
    print("\n--- Estatísticas da Sessão ---")
    if not palavras_estudo_final:
        print("Nenhuma palavra foi carregada ou estudada.")
        return

    for p_info in palavras_estudo_final:
        status = ""
        if p_info["masterizada"]:
            status = f"Masterizada (Acertos: {p_info['corretas']}, Erros: {p_info['incorretas']})"
        elif p_info["apresentada"]:
            status = f"Tentada (Acertos: {p_info['corretas']}, Erros: {p_info['incorretas']})"
        else:
            status = "Não estudada"
        print(f"- {p_info['texto']}: {status}")
    print("----------------------------")


def main():
    # --- Configuração de Argumentos da Linha de Comando ---
    import argparse
    parser = argparse.ArgumentParser(description="Programa de prática de digitação e audição em inglês com Piper TTS.")
    parser.add_argument(
        "arquivo_palavras",
        help="Caminho para o arquivo de texto contendo as palavras (uma palavra por linha)."
    )
    args = parser.parse_args() # Analisa os argumentos. Se inválidos, imprime help e sai.
    # --- Fim da Configuração de Argumentos ---

    # --- Carregar Palavras do Arquivo ---
    try:
        with open(args.arquivo_palavras, 'r', encoding='utf-8') as f:
            palavras_raw = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Erro: Arquivo de palavras não encontrado em '{args.arquivo_palavras}'")
        sys.exit(1) # Sai do programa com código de erro
    
    if not palavras_raw:
        print("O arquivo de palavras está vazio. Nada para estudar.")
        sys.exit(0)

    # Inicializar estrutura de dados para cada palavra
    palavras_estudo = []
    for p_texto in palavras_raw:
        palavras_estudo.append({
            "texto": p_texto,
            "corretas": 0,
            "incorretas": 0,
            "masterizada": False,
            "apresentada": False
        })

    if not verificar_piper():
        print("Por favor, configure o Piper corretamente antes de executar o programa.")
        return
    print("Bem-vindo ao programa de prática de digitação e audição em inglês (com Piper TTS)!")
    print("Ouça a palavra e digite-a corretamente.")

    # --- Configuração de Velocidade ---
    velocidades_opcoes = {
        "1": {"nome": "Muito Lento", "scale": 1.6},
        "2": {"nome": "Lento", "scale": 1.3},
        "3": {"nome": "Normal", "scale": 1.0},
        "4": {"nome": "Rápido", "scale": 0.7}
    }
    default_scale = velocidades_opcoes["3"]["scale"] # "Normal"

    print("\nPrimeiro, defina a velocidade da fala:")
    velocidade_selecionada_scale = selecionar_velocidade(velocidades_opcoes, default_scale)
    # --- Fim da Configuração de Velocidade ---

    print("-" * 20) # Separador visual

    # Loop principal de estudo
    try:
        while True:
            palavras_ativas = [p for p in palavras_estudo if not p["masterizada"]]
            if not palavras_ativas:
                print("\nParabéns! Todas as palavras foram masterizadas!")
                break # Sai do loop principal de estudo

            palavra_atual_obj = random.choice(palavras_ativas)
            palavra_correta = palavra_atual_obj["texto"]
            palavra_atual_obj["apresentada"] = True

            print(f"\n--- Próxima Palavra ---")
            print("Ouça com atenção...")
            if not falar_palavra_piper(palavra_correta, velocidade_selecionada_scale):
                print(f"Não foi possível falar a palavra '{palavra_correta}'. Pulando esta palavra por agora.")
                palavra_atual_obj["incorretas"] += 1 # Considera um erro se não puder ser falada
                continue

            tentativas = 0
            max_tentativas = 3
            palavra_adivinhada_nesta_rodada = False # Se acertou nesta apresentação específica

            while tentativas < max_tentativas:
                print("\nOpções:")
                print("  0 - Sair do programa")
                print("  1 - Alterar velocidade")
                print("  2 - Repetir a palavra")
                entrada_usuario = input(f"Digite a palavra que você ouviu (ou o número de uma opção): ").strip()

                if entrada_usuario == "0":
                    print("\nSaindo do programa...")
                    exibir_estatisticas(palavras_estudo)
                    return # Sai da função main
                elif entrada_usuario == "1":
                    nova_escala = selecionar_velocidade(velocidades_opcoes, velocidade_selecionada_scale)
                    if nova_escala is not None:
                        velocidade_selecionada_scale = nova_escala
                    print("\nOuça novamente com a nova velocidade...")
                    if not falar_palavra_piper(palavra_correta, velocidade_selecionada_scale):
                        print("Erro ao tentar falar a palavra com a nova velocidade.")
                    continue # Volta para o prompt de opções/palavra
                elif entrada_usuario == "2":
                    print("\nRepetindo a palavra...")
                    if not falar_palavra_piper(palavra_correta, velocidade_selecionada_scale):
                        print("Erro ao tentar repetir a palavra.")
                    continue # Volta para o prompt de opções/palavra
                else: # Usuário digitou uma palavra
                    palavra_digitada = entrada_usuario.lower()
                    if palavra_digitada == palavra_correta.lower():
                        print("Correto! 😄")
                        # print("Correto! !!!") # Alternativa para 🎉
                        exibir_trofeu()
                        falar_frase_feedback("Congratulations! You got the word right!", velocidade_selecionada_scale)
                        palavra_adivinhada_nesta_rodada = True
                        break # Sai do loop de tentativas (while), vai para a próxima palavra
                    else:
                        tentativas += 1
                        print(f"Incorreto. 😟 Tente novamente. ({max_tentativas - tentativas} tentativas restantes)")
                        if tentativas < max_tentativas:
                            print("\nRepetindo a palavra...") # Emoji 😟 removido
                            if not falar_palavra_piper(palavra_correta, velocidade_selecionada_scale):
                                print("Erro ao tentar repetir a palavra. Pulando para a próxima tentativa se houver.")
                        else:
                            print(f"Incorreto.") # Emoji 😟 removido
            
            # Após o loop de tentativas regulares
            if palavra_adivinhada_nesta_rodada:
                palavra_atual_obj["corretas"] += 1
            else:
                # Se não adivinhou nas tentativas regulares, oferece a dica
                print(f"\nVocê usou todas as {max_tentativas} tentativas regulares.")
                falar_frase_feedback("You used all your regular attempts. Here is a hint.", velocidade_selecionada_scale)
                print("Vamos tentar com uma dica!")
                dica = gerar_dica(palavra_correta)
                
                tentativas_com_dica = 0
                max_tentativas_com_dica = 3
                acertou_com_dica = False

                while tentativas_com_dica < max_tentativas_com_dica:
                    print(f"\nDica: {dica}")
                    print(f"Tentativa com dica {tentativas_com_dica + 1} de {max_tentativas_com_dica}.")
                    
                    print("Ouça novamente...")
                    if not falar_palavra_piper(palavra_correta, velocidade_selecionada_scale):
                        print("Erro ao tentar repetir a palavra. Tente digitar mesmo assim.")
                    
                    palavra_digitada_com_dica = input("Digite a palavra com a ajuda da dica: ").strip().lower()

                    if palavra_digitada_com_dica == palavra_correta.lower():
                        print("Correto com a dica! !!!") # 🎉 substituído por !!!
                        exibir_trofeu()
                        falar_frase_feedback("Congratulations! You got the word right with the hint!", velocidade_selecionada_scale)
                        acertou_com_dica = True
                        break
                    else:
                        tentativas_com_dica += 1
                        print("Incorreto. Tente novamente com a dica.") # Emoji 😟 removido
                
                if acertou_com_dica:
                    palavra_atual_obj["corretas"] += 1
                else:
                    print(f"\nVocê usou todas as tentativas com dica. A palavra correta era: '{palavra_correta}'")
                    palavra_atual_obj["incorretas"] += 1 # Emoji 😟 não estava aqui
                    falar_frase_feedback("You used all your hint attempts. Don't give up! Keep practicing!", velocidade_selecionada_scale)

            # Verificar e atualizar status de masterização
            if palavra_atual_obj["corretas"] >= MASTERY_THRESHOLD and not palavra_atual_obj["masterizada"]:
                palavra_atual_obj["masterizada"] = True
                print("\n****************************************") # ✨ já substituído por *
                print(f"Parabéns! Você masterizou a palavra '{palavra_correta}'! Ela não será mais apresentada.")
                exibir_trofeu()
                print("****************************************") # ✨ já substituído por *
                falar_frase_feedback(f"Congratulations! You have mastered the word {palavra_correta}!", velocidade_selecionada_scale)

        # Fim do loop while True (estudo)
        print("\nPrática concluída! 😄") # Emoji 😄 removido

    finally: # Garante que as estatísticas sejam exibidas mesmo em caso de erro inesperado ou Ctrl+C
        exibir_estatisticas(palavras_estudo)

if __name__ == "__main__":
    main()