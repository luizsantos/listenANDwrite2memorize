import sys
import os
import subprocess
import random
import json # Para salvar e carregar o progresso
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox, QComboBox,
    QTextEdit, QSizePolicy
)
from PyQt6.QtGui import QAction, QFont, QIcon, QMovie, QPixmap # QIcon para o futuro
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSize, pyqtSlot

# --- Configurações (podem vir de um arquivo de config ou settings dialog no futuro) ---
CAMINHO_EXECUTAVEL_PIPER_DEFAULT = "./piper/piper"
CAMINHO_MODELO_VOZ_ONNX_DEFAULT = "./piper_voices/en_US-hfc_female-medium.onnx"
MASTERY_THRESHOLD_DEFAULT = 2

# --- Lógica do Piper (Adaptada do seu script original) ---
# Idealmente, operações demoradas como esta rodariam em um QThread para não bloquear a GUI.
# Por simplicidade inicial, manteremos síncrono, mas com um aviso.

class PiperTTSWorker(QObject): # QObject para usar sinais
    finished_speaking = pyqtSignal(bool, str) # sucesso, mensagem_erro
    # Adicionar um sinal para iniciar a fala, que será conectado ao slot speak
    
    def __init__(self, piper_exe): # model_onnx não é mais passado no init
        super().__init__()
        self.piper_exe = piper_exe
        # self.model_onnx = model_onnx
        self.temp_wav_file = "output_gui.wav" # Nome de arquivo temporário diferente

    @pyqtSlot(str, float, str) # Adicionado model_path_to_use
    def speak(self, text, length_scale=1.0, model_path_to_use=None):
        if not model_path_to_use:
            self.finished_speaking.emit(False, "No voice model specified to speak.")
            return
        if not self._verificar_piper(model_path_to_use): # Passa o modelo específico para verificação
            self.finished_speaking.emit(False, f"Invalid Piper configuration for model: {os.path.basename(model_path_to_use)}")
            return

        comando_piper = [
            self.piper_exe,
            "--model", model_path_to_use,
            "--output_file", self.temp_wav_file,
            "--length_scale", str(length_scale)
        ]
        try:
            process = subprocess.Popen(comando_piper, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(input=text.encode('utf-8'))

            if process.returncode != 0:
                self.finished_speaking.emit(False, f"Piper Error: {stderr.decode('utf-8', errors='replace')}")
                return

            if not os.path.exists(self.temp_wav_file):
                self.finished_speaking.emit(False, "Error: Piper did not generate the audio file.")
                return

            # Tocar o áudio
            players = [
                {"name": "aplay", "path": "/usr/bin/aplay", "args": ["-q", self.temp_wav_file]},
                {"name": "paplay", "path": "/usr/bin/paplay", "args": [self.temp_wav_file]},
            ]
            player_funcionou = False
            ultimo_erro_player = "No audio player found/worked."

            for player_info in players:
                if os.path.exists(player_info["path"]):
                    comando_player = [player_info["path"]] + player_info["args"]
                    resultado_player = subprocess.run(comando_player, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
                    if resultado_player.returncode == 0:
                        player_funcionou = True
                        break
                    else:
                        ultimo_erro_player = f"Error with {player_info['name']}: {resultado_player.stderr.strip() or resultado_player.stdout.strip()}"
            
            if player_funcionou:
                self.finished_speaking.emit(True, "")
            else:
                self.finished_speaking.emit(False, ultimo_erro_player)

        except FileNotFoundError:
            self.finished_speaking.emit(False, f"Piper executable not found at '{self.piper_exe}'.")
        except Exception as e:
            self.finished_speaking.emit(False, f"Unexpected error while speaking: {e}")
        finally:
            if os.path.exists(self.temp_wav_file):
                try:
                    os.remove(self.temp_wav_file)
                except OSError:
                    pass # Ignore error when removing temporary file

    def _verificar_piper(self, model_path_to_check): # Agora recebe o caminho do modelo para verificar
        if not os.path.exists(self.piper_exe):
            print(f"Error: Piper executable not found at '{self.piper_exe}'")
            return False
        if not os.path.exists(model_path_to_check):
            print(f"Error: ONNX voice model not found at '{model_path_to_check}'")
            return False
        return True

# --- Gerenciador de Palavras ---
class WordManager:
    def __init__(self):
        self.words_data = []  # Lista de dicionários
        self.current_word_obj = None
        self.mastery_threshold = MASTERY_THRESHOLD_DEFAULT

    def load_words_from_file(self, filepath):
        self.words_data = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_words = [line.strip() for line in f if line.strip()]
            for text in raw_words:
                self.words_data.append({
                    "text": text, "correct": 0, "incorrect": 0,
                    "mastered": False, "presented": False
                })
            return True, f"{len(self.words_data)} words loaded."
        except FileNotFoundError:
            return False, "File not found."
        except Exception as e:
            return False, f"Error loading words: {e}"

    def load_progress_data(self, progress_data_list):
        """Carrega o progresso (acertos, erros, etc.) para as palavras existentes."""
        if not self.words_data:
            return False, "No base words loaded to apply progress to."
        
        progress_map = {item['text']: item for item in progress_data_list}
        for word_obj in self.words_data:
            if word_obj['text'] in progress_map:
                progress_item = progress_map[word_obj['text']]
                word_obj.update(progress_item) # Atualiza com os dados do progresso
        return True, "Progress loaded."

    def get_progress_data_to_save(self):
        """Retorna os dados das palavras formatados para salvar."""
        return self.words_data # A estrutura atual já é adequada

    def reset_all_word_stats(self):
        """Resets the statistics for all loaded words."""
        for word_obj in self.words_data:
            word_obj["correct"] = 0
            word_obj["incorrect"] = 0
            word_obj["mastered"] = False
            word_obj["presented"] = False
        print("All word statistics have been reset.")

    def get_next_word(self):
        active_words = [w for w in self.words_data if not w["mastered"]]
        if not active_words:
            self.current_word_obj = None
            return None
        self.current_word_obj = random.choice(active_words)
        self.current_word_obj["presented"] = True
        return self.current_word_obj

    def record_attempt(self, correct_attempt):
        if not self.current_word_obj:
            return
        if correct_attempt:
            self.current_word_obj["correct"] += 1
            if self.current_word_obj["correct"] >= self.mastery_threshold:
                self.current_word_obj["mastered"] = True
        else:
            self.current_word_obj["incorrect"] += 1
        
    def get_stats_summary(self):
        if not self.words_data: return "No words loaded."
        total_words = len(self.words_data)
        presented_count = sum(1 for w in self.words_data if w["presented"])
        mastered_count = sum(1 for w in self.words_data if w["mastered"])
        total_correct_attempts = sum(w['correct'] for w in self.words_data)
        total_incorrect_attempts = sum(w['incorrect'] for w in self.words_data)
        return (f"Words: {total_words} | Presented: {presented_count} | Mastered: {mastered_count}\n"
                f"Correct (attempts): {total_correct_attempts} | Incorrect (words missed after hints): {total_incorrect_attempts}")

    def get_full_stats(self):
        stats_lines = []
        for p_info in self.words_data:
            status = ""
            if p_info["mastered"]:
                status = f"Mastered (Correct: {p_info['correct']}, Incorrect: {p_info['incorrect']})"
            elif p_info["presented"]:
                status = f"Attempted (Correct: {p_info['correct']}, Incorrect: {p_info['incorrect']})"
            else:
                status = "Not studied"
            stats_lines.append(f"- {p_info['text']}: {status}")
        return "\n".join(stats_lines) if stats_lines else "No statistics available."

    def get_mastered_words_texts(self):
        return [w['text'] for w in self.words_data if w['mastered']]


class GifPopupWindow(QWidget):
    def __init__(self, image_directory, duration_ms=4000, parent=None, max_display_width=450, max_display_height=450):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen) # Sem bordas, fica no topo
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # Ensure widget is deleted when closed
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # Para cantos arredondados se a imagem tiver

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0) # Sem margens internas no layout
        self.image_label = QLabel(self)
        layout.addWidget(self.image_label)

        self.movie = None
        gif_files = []
        if os.path.isdir(image_directory):
            gif_files = [f for f in os.listdir(image_directory) if f.lower().endswith(".gif")]
        
        if not gif_files:
            print(f"Warning: No .gif files found in '{image_directory}'.")
            self.image_label.setText(f"No GIFs in\n{image_directory}")
            self.image_label.setFixedSize(200,100) # Default size for error message
        else:
            chosen_gif_name = random.choice(gif_files)
            image_path = os.path.join(image_directory, chosen_gif_name)
            print(f"Displaying GIF: {image_path}")

            self.movie = QMovie(image_path)
            if not self.movie.isValid() or self.movie.frameCount() == 0:
                print(f"Error: QMovie is not valid or has no frames for '{image_path}'. Error: {self.movie.lastErrorString()}")
                self.image_label.setText(f"Error loading GIF:\n{os.path.basename(image_path)}")
                self.image_label.setFixedSize(200,100)
            else:
                # Tenta obter o tamanho original do primeiro frame para escalar
                original_size = self.movie.currentPixmap().size()
                if original_size.isEmpty(): # Fallback se o tamanho não puder ser determinado
                    original_size = QSize(max_display_width, max_display_height)

                # Escala mantendo a proporção para caber em max_display_width/height
                scaled_size = original_size.scaled(max_display_width, max_display_height, Qt.AspectRatioMode.KeepAspectRatio)
                
                self.movie.setScaledSize(scaled_size)
                self.image_label.setMovie(self.movie)
                self.movie.start()
                if self.movie.state() == QMovie.MovieState.NotRunning and self.movie.lastError() != QMovie.NoError:
                     print(f"QMovie did not start. Error: {self.movie.lastErrorString()}")
                
                # Ajusta o tamanho do label e da janela
                self.image_label.setFixedSize(scaled_size)
                self.setFixedSize(scaled_size) # Define o tamanho da janela para o tamanho do GIF escalado

        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # self.adjustSize() # Não é mais necessário se setFixedSize for usado

        QTimer.singleShot(duration_ms, self.close)

    def closeEvent(self, event):
        if self.movie and self.movie.state() != QMovie.MovieState.NotRunning:
            self.movie.stop()
        super().closeEvent(event)

# --- Abas da Interface ---
class BaseTab(QWidget):
    request_speak_signal = pyqtSignal(str, float, str) # Adicionado model_path

    def __init__(self, piper_worker, word_manager, main_window_ref):
        super().__init__()
        self.piper_worker = piper_worker
        self.word_manager = word_manager
        self.main_window_ref = main_window_ref # Para acessar velocidade, etc.
        self.current_word_text = None
        
        self.max_normal_attempts = 2
        self.current_normal_attempts_left = self.max_normal_attempts
        self.hint_level = 0 # 0: no hint, 1: underscores, 2: first/last, 3: 60%
        self.max_hint_level = 3 # Corresponds to 3 hint attempts / levels
        self.force_correct_typing_mode = False
        self.word_to_force_type = None

        # Conectar o sinal local ao slot do piper_worker (já estava correto)
        # Esta conexão é feita uma vez por instância de BaseTab
        self.request_speak_signal.connect(self.piper_worker.speak)
        # O piper_worker já está em um thread gerenciado pela MainWindow
        self.piper_worker.finished_speaking.connect(self.on_piper_finished)

    def speak_text(self, text):
        speed_scale = self.main_window_ref.get_current_speed_scale()
        effective_voice_model_path = self.main_window_ref.get_effective_voice_model_path()
        if effective_voice_model_path:
            self.request_speak_signal.emit(text, speed_scale, effective_voice_model_path) # Emitir o sinal com o modelo
        
    def speak_system_feedback(self, text):
        """Fala uma frase de feedback do sistema sempre em velocidade Normal."""
        normal_speed_scale = self.main_window_ref.speed_options.get("Normal", 1.0) # Garante que pegamos a escala normal
        effective_voice_model_path = self.main_window_ref.get_effective_voice_model_path()
        if effective_voice_model_path:
            self.request_speak_signal.emit(text, normal_speed_scale, effective_voice_model_path)
        

    def on_piper_finished(self, success, message):
        if not success:
            self.show_feedback(f"Audio Error: {message}", error=True)
        # A aba específica pode querer fazer algo mais aqui

    def show_feedback(self, message, error=False):
        # Cada aba implementará seu próprio label de feedback
        pass

    def get_hint(self, word):
        n = len(word)
        if n == 0: return ""
        if n == 1 and self.hint_level >= 1 : return word # For single letter words, hint reveals it

        if self.hint_level == 1: # Only underscores
            return " ".join(["_"] * n)
        
        elif self.hint_level == 2: # First and last
            if n <= 2: # For words like "at", hint 2 becomes "a _"
                return " ".join(list(word[0] + "_" * (n-1))) if n > 0 else ""
            components = [word[0]]
            components.extend(["_"] * (n - 2))
            components.append(word[-1])
            return " ".join(components)

        elif self.hint_level == 3: # Approx 60% reveal
            if n <= 2: # For short words, reveal all
                return " ".join(list(word))

            num_to_reveal = int(n * 0.6)
            if num_to_reveal == 0 and n > 0: num_to_reveal = 1
            # Ensure at least first and last are shown if possible, and count them
            # towards num_to_reveal if they are part of the 60% target.
            
            revealed_indices = set()
            # Always try to reveal first and last
            if n > 0: revealed_indices.add(0)
            if n > 1: revealed_indices.add(n - 1)

            # Get other indices to reveal, avoiding first and last if already added
            other_indices = [i for i in range(n) if i not in revealed_indices]
            random.shuffle(other_indices)

            # Add more indices until num_to_reveal is met or no more indices
            while len(revealed_indices) < num_to_reveal and other_indices:
                revealed_indices.add(other_indices.pop())
            
            hint_list = []
            for i, char in enumerate(word):
                if i in revealed_indices:
                    hint_list.append(char)
                else:
                    hint_list.append("_")
            return " ".join(hint_list)
        
        return " ".join(["_"] * n) # Default or unknown level
    # def cleanup(self): # Não gerencia mais o thread aqui


class DictationTab(BaseTab):
    def __init__(self, piper_worker, word_manager, main_window_ref):
        super().__init__(piper_worker, word_manager, main_window_ref)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.instruction_label = QLabel("Listen to the word and type it below:")
        self.instruction_label.setFont(QFont("Arial", 14))
        layout.addWidget(self.instruction_label)

        self.play_button = QPushButton("▶️ &Speak Word")
        self.play_button.setFont(QFont("Arial", 12))
        self.play_button.clicked.connect(self.play_current_word_audio)
        layout.addWidget(self.play_button)

        self.input_field = QLineEdit()
        self.input_field.setFont(QFont("Arial", 16))
        self.input_field.returnPressed.connect(self.check_answer) # Enter para submeter
        layout.addWidget(self.input_field)

        self.submit_button = QPushButton("&Check")
        self.submit_button.setFont(QFont("Arial", 12))
        self.submit_button.clicked.connect(self.check_answer)
        layout.addWidget(self.submit_button)
        
        self.hint_label = QLabel("")
        self.hint_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(self.hint_label)

        self.feedback_label = QLabel("Load a word file to begin.")
        self.feedback_label.setFont(QFont("Arial", 12))
        self.feedback_label.setWordWrap(True)
        layout.addWidget(self.feedback_label)
        
        self.stats_summary_label = QLabel("")
        self.stats_summary_label.setFont(QFont("Arial", 10))
        layout.addWidget(self.stats_summary_label)

        self.mastered_words_title_label = QLabel("Mastered Words:")
        self.mastered_words_title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.mastered_words_title_label)
        self.mastered_words_label = QLabel("None yet.")
        self.mastered_words_label.setFont(QFont("Arial", 10))
        self.mastered_words_label.setWordWrap(True)
        layout.addWidget(self.mastered_words_label)
        
        # self.trophy_label = QLabel("") # Não vamos mais usar o label de texto para o troféu
        # self.trophy_label.setFont(QFont("Monospace", 10))
        # self.trophy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Definir uma altura mínima para garantir que o troféu tenha espaço
        # self.trophy_label.setMinimumHeight(120)
        # layout.addWidget(self.trophy_label)

        self.setLayout(layout)
        self.update_ui_for_new_word() # Estado inicial

    def show_feedback(self, message, error=False):
        self.feedback_label.setText(message)
        self.feedback_label.setStyleSheet("color: red;" if error else "color: green;")

    def load_new_word(self):
        self.current_word_text = None
        self.hint_label.setText("")
        self.hint_level = 0 # Reset hint level
        self.force_correct_typing_mode = False # Reset force typing mode
        self.word_to_force_type = None

        word_obj = self.word_manager.get_next_word()
        if word_obj:
            self.current_word_text = word_obj["text"]
            self.current_normal_attempts_left = self.max_normal_attempts # Reset normal attempts
            # Define o feedback inicial para uma nova palavra
            self.show_feedback(f"Listen and type. Attempts left: {self.current_normal_attempts_left}")
            # A mensagem de feedback será definida pelo método que chamou load_new_word
            # ou pelo play_current_word_audio se for a primeira vez.
        elif self.word_manager.words_data: # Há palavras carregadas, mas todas masterizadas
            self.show_feedback("Congratulations! All words have been mastered!", error=False)
            self.current_word_text = None # Garante que não há palavra ativa
        else:
            self.show_feedback("All words mastered or no words loaded!", error=False)
            self.current_word_text = None # Garante que não há palavra ativa
            
        self.update_ui_for_new_word()
        self.update_stats_summary()

    def update_ui_for_new_word(self):
        has_word = bool(self.current_word_text)
        self.play_button.setEnabled(has_word)
        self.input_field.setEnabled(has_word)
        self.submit_button.setEnabled(has_word)
        self.input_field.clear()
        if has_word:
            self.input_field.setFocus()
        
        # Habilita o botão de play se houver palavras disponíveis, mesmo que current_word_text seja None
        # Isso permite iniciar a primeira palavra após carregar o arquivo.
        can_play_new_word = bool(self.word_manager.words_data and [w for w in self.word_manager.words_data if not w['mastered']])
        self.play_button.setEnabled(can_play_new_word or has_word)


    def update_stats_summary(self):
        self.stats_summary_label.setText(self.word_manager.get_stats_summary())
        mastered_list = self.word_manager.get_mastered_words_texts()
        if mastered_list:
            self.mastered_words_label.setText(" - ".join(mastered_list))
        else:
            self.mastered_words_label.setText("None yet.")


    def check_answer(self):
        if not self.current_word_text:
            return

        typed_word = self.input_field.text().strip().lower()

        if self.force_correct_typing_mode:
            if typed_word == self.word_to_force_type.lower():
                self.show_feedback("Correct! You typed the word.")
                self.speak_system_feedback(f"Good. The word was {self.word_to_force_type}.") # Usa velocidade normal
                self.force_correct_typing_mode = False
                self.word_to_force_type = None
                self.current_word_text = None 
                self.update_ui_for_new_word()
            else:
                self.show_feedback(f"Please type the correct word: '{self.word_to_force_type}'", error=True)
                self.speak_system_feedback(f"Please type the word {self.word_to_force_type} correctly.") # Usa velocidade normal
            return # Fim do processamento para este modo

        # Esta é a lógica de verificação de resposta, movida da duplicata de play_current_word_audio
        correct_word_lower = self.current_word_text.lower()

        if typed_word == correct_word_lower:
            self.show_feedback("Correct!!!")
            # self.trophy_label.setText(get_trophy_ascii()) # Substituído pela janela de imagem
            self.gif_popup = GifPopupWindow(image_directory="img/", parent=self.main_window_ref)
            self.gif_popup.move(self.main_window_ref.geometry().center() - self.gif_popup.rect().center())
            self.gif_popup.show()
            self.speak_system_feedback("Congratulations! You got the word right!") # Usa velocidade normal
            self.word_manager.record_attempt(True)
            self.main_window_ref.update_student_level() # Informa acerto para atualizar nível
            if self.word_manager.current_word_obj and self.word_manager.current_word_obj["mastered"]:
                 self.show_feedback(f"Word '{self.current_word_text}' MASTERED!")
                 self.speak_system_feedback(f"You have mastered the word {self.current_word_text}!") # Usa velocidade normal
            # Prepara para a próxima palavra, mas não a carrega/fala automaticamente aqui.
            # O usuário clicará em "Tocar Palavra" novamente.
            self.current_word_text = None # Sinaliza que a palavra atual foi concluída
            self.play_current_word_audio() # Carrega e toca automaticamente a próxima palavra
        else:
            # Lógica de erro, transição para dicas, ou modo de forçar digitação
            if self.hint_level > 0: # Já está no modo de dica
                self.hint_level += 1 # Avança para o próximo nível de dica (ou excede)
                if self.hint_level <= self.max_hint_level:
                    new_hint = self.get_hint(self.current_word_text) # get_hint usa self.hint_level
                    self.hint_label.setText(f"Hint ({self.hint_level -1}/{self.max_hint_level-1}): {new_hint}") # Ajustar display de contagem
                    self.show_feedback(f"Incorrect. Try with the new hint.", error=True)
                    self.speak_text(self.current_word_text) # Repete a palavra, não reinicia o ciclo de tentativas
                else:
                    # Todas as tentativas de dica foram usadas
                    self.show_feedback(f"End of hint attempts. The word was: '{self.current_word_text}'", error=True)
                    self.speak_system_feedback(f"You used all your hint attempts. The word was {self.current_word_text}. Please type it now.") # Usa velocidade normal
                    self.word_manager.record_attempt(False)
                    self.main_window_ref.update_student_level(correct_streak_ended=True) # Informa erro para resetar nível
                    
                    self.error_gif_popup = GifPopupWindow(image_directory="img/errors/", parent=self.main_window_ref)
                    self.error_gif_popup.move(self.main_window_ref.geometry().center() - self.error_gif_popup.rect().center())
                    self.error_gif_popup.show()
                    
                    self.force_correct_typing_mode = True
                    self.word_to_force_type = self.current_word_text
                    self.hint_label.setText(f"TYPE THE WORD: {self.current_word_text}")
                    # Não limpa current_word_text aqui, pois o usuário precisa vê-lo para digitar
                    # A UI será atualizada para refletir o modo de forçar digitação

            else: # Tentativas normais (hint_level == 0)
                self.current_normal_attempts_left -= 1
                if self.current_normal_attempts_left > 0:
                    self.show_feedback(f"Incorrect. Attempts left: {self.current_normal_attempts_left}", error=True)
                    self.speak_text(self.current_word_text) # Repete a palavra
                else: # Tentativas normais esgotadas, entra no modo de dica
                    self.hint_level = 1 # Define o primeiro nível de dica
                    hint = self.get_hint(self.current_word_text) # get_hint usa self.hint_level
                    self.hint_label.setText(f"Hint (1/{self.max_hint_level-1}): {hint}") # Ajustar display de contagem
                    self.show_feedback(f"Normal attempts exhausted. Try with the hint!", error=True)
                    self.speak_system_feedback("You used all your regular attempts. Here is a hint.") # Usa velocidade normal
                    self.speak_text(self.current_word_text) # Repete a palavra para a primeira tentativa com dica
        
        # Após o check_answer, se uma palavra estava ativa, ela foi processada.
        # A lógica de limpar current_word_text já está nos branches de acerto e esgotamento de tentativas.
        self.input_field.selectAll()
        self.input_field.setFocus()
        self.update_stats_summary()

    def play_current_word_audio(self):
        if not self.current_word_text: # Se nenhuma palavra está ativa na aba
            self.load_new_word()       # Tenta carregar a próxima/primeira palavra
                                       # load_new_word já reseta tentativas/dicas e define feedback inicial
            if not self.current_word_text: # Se ainda não há palavra (ex: todas masterizadas ou nenhuma carregada)
                # self.show_feedback já foi chamado por load_new_word
                self.update_ui_for_new_word() # Garante que botões de input estão desabilitados
                return
        
        # Neste ponto, uma palavra está carregada (self.current_word_text está definido)
        # Se era uma nova palavra, load_new_word resetou os estados.
        # Se era uma palavra existente (meio das dicas), os estados permanecem.
        self.speak_text(self.current_word_text)
        self.input_field.setFocus()
        # Não limpa input_field ou hint_label aqui, pois o usuário pode estar apenas repetindo o áudio.
        # O feedback de tentativas/dicas também não é alterado aqui, pois é gerenciado por load_new_word ou check_answer.
        self.update_ui_for_new_word() # Garante que o estado da UI está correto (ex: campo de entrada habilitado)


class SpellingTab(BaseTab):
    def __init__(self, piper_worker, word_manager, main_window_ref):
        super().__init__(piper_worker, word_manager, main_window_ref)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.instruction_label = QLabel("Listen to the spelling and type the word:")
        self.instruction_label.setFont(QFont("Arial", 14))
        layout.addWidget(self.instruction_label)

        self.play_spell_button = QPushButton("▶️ &Spell Word")
        self.play_spell_button.setFont(QFont("Arial", 12))
        self.play_spell_button.clicked.connect(self.play_current_word_spelling)
        layout.addWidget(self.play_spell_button)

        self.input_field = QLineEdit()
        self.input_field.setFont(QFont("Arial", 16))
        self.input_field.returnPressed.connect(self.check_spelled_answer)
        layout.addWidget(self.input_field)

        self.submit_button = QPushButton("C&heck Word")
        self.submit_button.setFont(QFont("Arial", 12))
        self.submit_button.clicked.connect(self.check_spelled_answer)
        layout.addWidget(self.submit_button)

        self.feedback_label = QLabel("Load a word file to begin.")
        self.feedback_label.setFont(QFont("Arial", 12))
        self.feedback_label.setWordWrap(True)
        layout.addWidget(self.feedback_label)

        self.stats_summary_label = QLabel("")
        self.stats_summary_label.setFont(QFont("Arial", 10))
        layout.addWidget(self.stats_summary_label)

        self.mastered_words_title_label = QLabel("Mastered Words:")
        self.mastered_words_title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.mastered_words_title_label)
        self.mastered_words_label = QLabel("None yet.")
        self.mastered_words_label.setFont(QFont("Arial", 10))
        self.mastered_words_label.setWordWrap(True)
        layout.addWidget(self.mastered_words_label)
        # self.trophy_label = QLabel("") # Não vamos mais usar o label de texto para o troféu
        # self.trophy_label.setFont(QFont("Monospace", 10))
        # self.trophy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Definir uma altura mínima para garantir que o troféu tenha espaço
        # self.trophy_label.setMinimumHeight(120)
        # layout.addWidget(self.trophy_label)

        self.setLayout(layout)
        self.update_ui_for_new_word()

    def show_feedback(self, message, error=False):
        self.feedback_label.setText(message)
        self.feedback_label.setStyleSheet("color: red;" if error else "color: green;")

    def load_new_word(self): # Similar à DictationTab, mas chama play_current_word_spelling
        self.current_word_text = None
        # self.trophy_label.setText("") # Não é mais necessário
        word_obj = self.word_manager.get_next_word() # Usa o mesmo método por enquanto
        if word_obj:
            self.current_word_text = word_obj["text"]
            self.current_normal_attempts_left = self.max_normal_attempts # Usa as variáveis da BaseTab
            # Define o feedback inicial para uma nova palavra
            self.show_feedback(f"Listen to the spelling. Attempts left: {self.current_normal_attempts_left}")
            # A mensagem de feedback será definida pelo método que chamou load_new_word
            # ou pelo play_current_word_spelling se for a primeira vez.
        elif self.word_manager.words_data: # Há palavras carregadas, mas todas masterizadas
            self.show_feedback("Congratulations! All words have been mastered!", error=False)
            self.current_word_text = None
        else:
            self.show_feedback("All words mastered or no words loaded!", error=False)
            self.current_word_text = None
        self.update_ui_for_new_word()
        self.update_stats_summary()

    def update_ui_for_new_word(self):
        has_word = bool(self.current_word_text)
        self.play_spell_button.setEnabled(has_word)
        self.input_field.setEnabled(has_word)
        self.submit_button.setEnabled(has_word)
        self.input_field.clear()
        if has_word:
            self.input_field.setFocus()
        
        can_play_new_word = bool(self.word_manager.words_data and [w for w in self.word_manager.words_data if not w['mastered']])
        self.play_spell_button.setEnabled(can_play_new_word or has_word)

            
    def update_stats_summary(self):
        self.stats_summary_label.setText(self.word_manager.get_stats_summary())
        mastered_list = self.word_manager.get_mastered_words_texts()
        if mastered_list:
            self.mastered_words_label.setText(" - ".join(mastered_list))
        else:
            self.mastered_words_label.setText("None yet.")


    def check_spelled_answer(self):
        if not self.current_word_text:
            return

        # Esta é a lógica de verificação de resposta, movida da duplicata de play_current_word_spelling
        typed_word = self.input_field.text().strip().lower()
        correct_word_lower = self.current_word_text.lower()

        if typed_word == correct_word_lower:
            self.show_feedback("Correct!!!")
            # self.trophy_label.setText(get_trophy_ascii()) # Substituído pela janela de imagem
            self.gif_popup = GifPopupWindow(image_directory="img/", parent=self.main_window_ref)
            self.gif_popup.move(self.main_window_ref.geometry().center() - self.gif_popup.rect().center())
            self.gif_popup.show()
            self.speak_system_feedback("Well done! That's the correct spelling!") # Usa velocidade normal
            self.word_manager.record_attempt(True) # Assume mesma lógica de acerto
            self.main_window_ref.update_student_level() # Informa acerto para atualizar nível
            if self.word_manager.current_word_obj and self.word_manager.current_word_obj["mastered"]:
                 self.show_feedback(f"Word '{self.current_word_text}' MASTERED!")
                 self.speak_system_feedback(f"You have mastered the spelling of {self.current_word_text}!") # Usa velocidade normal
            self.current_word_text = None # Sinaliza que a palavra atual foi concluída
            self.play_current_word_spelling() # Carrega e soletra automaticamente a próxima palavra
        else:
            # self.trophy_label.setText("") # Não é mais necessário
            self.current_normal_attempts_left -=1
            if self.current_normal_attempts_left > 0:
                self.show_feedback(f"Incorrect. Try spelling again. Attempts: {self.current_normal_attempts_left}", error=True)
                self.play_current_word_spelling()
            else:
                self.show_feedback(f"Incorrect. The word was: {self.current_word_text}", error=True)
                self.speak_system_feedback("That was not correct. Keep practicing your spelling!") # Usa velocidade normal
                
                # Mostra GIF de erro também na aba de soletrar se esgotar tentativas
                self.error_gif_popup = GifPopupWindow(image_directory="img/errors/", parent=self.main_window_ref)
                self.error_gif_popup.move(self.main_window_ref.geometry().center() - self.error_gif_popup.rect().center())
                self.error_gif_popup.show()
                
                self.word_manager.record_attempt(False) 
                self.main_window_ref.update_student_level(correct_streak_ended=True) # Informa erro para resetar nível
                self.current_word_text = None
                self.update_ui_for_new_word()
        self.input_field.selectAll()
        self.input_field.setFocus()
        self.update_stats_summary()

    def play_current_word_spelling(self):
        if not self.current_word_text: # Se nenhuma palavra está ativa na aba
            self.load_new_word()       # Tenta carregar a próxima/primeira palavra
            if not self.current_word_text: # Se ainda não há palavra (ex: todas masterizadas ou nenhuma carregada)
                # self.show_feedback já foi chamado por load_new_word
                return
        
        # Neste ponto, uma palavra está carregada (self.current_word_text está definido)
        # Se era uma nova palavra, load_new_word resetou os estados.
        # Se era uma palavra existente, os estados permanecem.
        spelled_word_with_pause = ", ".join(list(self.current_word_text)) + "."
        self.speak_text(spelled_word_with_pause)
        self.input_field.setFocus()
        # Não limpa input_field aqui.
        # O feedback de tentativas também não é alterado aqui.
        self.update_ui_for_new_word() # Garante que o estado da UI está correto


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        title_label = QLabel("listenANDwrite2memorize")
        title_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        version_label = QLabel("Version 0.2.0") # Assuming a version bump
        version_label.setFont(QFont("Arial", 12))
        layout.addWidget(version_label, alignment=Qt.AlignmentFlag.AlignCenter)

        description_text = QTextEdit()
        description_text.setReadOnly(True)
        description_text.setFont(QFont("Arial", 11))
        # Translated and updated "About" text
        description_text.setText(
            "<b>listenANDwrite2memorize</b> is an interactive program designed to help practice "
            "dictation and spelling of English words, using the Piper Text-to-Speech (TTS) system "
            "for an authentic auditory experience.\n\n"
            "Features:\n"
            "<ul>"
            "<li><b>Interactive Dictation:</b> Listen to words and type them, with immediate feedback.</li>"
            "<li><b>Spelling Practice:</b> Listen to spelled words and write them.</li>"
            "<li><b>Word Import:</b> Load your own word lists from text files (.txt).</li>"
            "<li><b>Speech Speed Control:</b> Adjust pronunciation speed (Very Slow, Slow, Normal, Fast) or use Random mode.</li>"
            "<li><b>Voice Selection:</b> Choose between different voices and accents (e.g., US Woman, GB Man) or use Random mode.</li>"
            "<li><b>Progressive Hint System (Dictation):</b> Get gradual help if you have difficulties:"
            "  <ul>"
            "    <li>Hint 1: Shows the number of characters (e.g., _ _ _ _ _).</li>"
            "    <li>Hint 2: Shows the first and last letter (e.g., h _ _ _ o).</li>"
            "    <li>Hint 3: Reveals approximately 60% of the word.</li>"
            "  </ul>"
            "</li>"
            "<li><b>Learning Reinforcement:</b> If you miss all attempts, you must type the correct word to proceed.</li>"
            "<li><b>Level System:</b> Progress from Noob to God based on your consecutive correct answers, with visual feedback.</li>"
            "<li><b>Random Visual Feedback:</b> Fun GIFs for correct answers and errors.</li>"
            "<li><b>Progress History:</b> Save and continue your learning from where you left off, or reset the progress for a file.</li>"
            "<li><b>Keyboard Shortcuts:</b> For ease of use.</li>"
            "</ul>"
            "<b>Developed by:</b> Luiz Arthur Feitosa dos Santos<br>"
            "<b>Contact:</b> <a href='mailto:luizsantos@utfpr.edu.br'>luizsantos@utfpr.edu.br</a><br><br>"
            "This program is distributed under the GNU General Public License (GPL), version 3 or later.<br>"
            "For more details on the license, visit: <a href='https://www.gnu.org/licenses/gpl-3.0.html'>https://www.gnu.org/licenses/gpl-3.0.html</a>"
        )
        # Para ajustar a altura do QTextEdit ao conteúdo, pode ser um pouco complexo.
        # Removida a altura fixa para permitir que o QTextEdit expanda.
        # description_text.setFixedHeight(200) 
        
        # Estilo para parecer um label e não um campo de edição
        description_text.setStyleSheet("""
            QTextEdit {
                background-color: transparent; /* Ou use um cinza específico: #f0f0f0; */
                border: none; /* Remove a borda */
            }
        """)
        layout.addWidget(description_text)
        
        self.setLayout(layout)

# --- Janela Principal ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("listenANDwrite2memorize - English Practice")
        self.setGeometry(100, 100, 700, 550) # x, y, largura, altura

        # Inicializar lógica principal
        # TODO: Permitir configuração dos caminhos do Piper via GUI ou arquivo de config
        self.piper_worker = PiperTTSWorker(CAMINHO_EXECUTAVEL_PIPER_DEFAULT) # model_onnx não é mais passado aqui
        self.word_manager = WordManager()
        
        # Configurar o thread para o PiperTTSWorker
        self.tts_thread = QThread(self) # Passar 'self' como pai para gerenciamento
        self.piper_worker.moveToThread(self.tts_thread)

        # Conexões para o ciclo de vida do thread
        self.tts_thread.finished.connect(self.piper_worker.deleteLater) # Limpar o worker quando o thread terminar
        # self.tts_thread.started.connect(self.piper_worker.algum_metodo_de_inicializacao_no_thread) # Se necessário
        self.tts_thread.start()

        # --- Gerenciamento de Nível do Aluno ---
        # Este bloco DEVE vir ANTES da chamada a self._create_widgets()
        self.consecutive_correct_answers = 0 # Contador de acertos seguidos
        self.student_levels = {0: "Noob", 2: "Pro", 4: "Hacker", 8: "God"} # Nomes dos níveis atualizados
        self.student_level_colors = {"Noob": "grey", "Pro": "green", "Hacker": "GoldenRod", "God": "orange"} # Cores atualizadas (Hacker agora é GoldenRod)
        self.current_student_level_name = "Noob" # Nível inicial atualizado
        
        self.voice_models = {
            "Random": "random_voice", 
            "Woman (US)": CAMINHO_MODELO_VOZ_ONNX_DEFAULT,
            "Man (GB)": "./piper_voices/en_GB-alan-medium.onnx"
        }
        self.current_selected_voice_name = "Woman (US)" 

        self.speed_options = { # Renomeado de speed_map para clareza
            "Random": "random_speed", 
            "Very Slow": 1.6, "Slow": 1.3, "Normal": 1.0, "Fast": 0.7
        }
        self.current_selected_speed_name = "Normal" # Nome da velocidade selecionada
        
        self.current_word_file_path = None # Para rastrear o arquivo de palavras carregado
        self.WORDLISTS_DIR_NAME = "wordlists" # Nome do diretório para listas de palavras e progresso
        os.makedirs(self.WORDLISTS_DIR_NAME, exist_ok=True) # Cria o diretório se não existir

        # --- Fim do Gerenciamento de Nível ---

        self._create_widgets()
        self._create_menus()
        self._create_toolbar() # Para controle de velocidade

        self.show()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
        
        # Layout principal para incluir o label de nível e as abas
        main_layout = QVBoxLayout()
        
        self.level_display_label = QLabel(f"Level: {self.current_student_level_name}")
        font = QFont("Arial", 24, QFont.Weight.Bold)
        self.level_display_label.setFont(font)
        self.level_display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.level_display_label.setStyleSheet(f"color: {self.student_level_colors[self.current_student_level_name]}; padding: 10px;")
        self._apply_level_style_to_tabs() # Aplica o estilo inicial às abas
        main_layout.addWidget(self.level_display_label)
        
        main_layout.addWidget(self.tab_widget)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)


        # Criar abas
        self.dictation_tab = DictationTab(self.piper_worker, self.word_manager, self)
        self.spelling_tab = SpellingTab(self.piper_worker, self.word_manager, self)
        self.about_tab = AboutTab()

        self.tab_widget.addTab(self.dictation_tab, "Dictation")
        self.tab_widget.addTab(self.spelling_tab, "Spelling")
        self.tab_widget.addTab(self.about_tab, "About")

    def _create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        import_action = QAction("&Import Word File...", self)
        import_action.triggered.connect(self.import_word_file_dialog)
        file_menu.addAction(import_action)

        self.reset_progress_action = QAction("&Reset Progress for Current File", self)
        self.reset_progress_action.triggered.connect(self.reset_current_progress_dialog)
        self.reset_progress_action.setEnabled(False) # Habilitar após carregar um arquivo
        file_menu.addAction(self.reset_progress_action)

        
        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close) # Chama o closeEvent
        file_menu.addAction(exit_action)
        
        # TODO: Menu de Configurações (para caminhos do Piper, etc.)

    def _create_toolbar(self):
        toolbar = self.addToolBar("Controles")
        
        toolbar.addWidget(QLabel("Speech Speed: "))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(list(self.speed_options.keys()))
        self.speed_combo.setCurrentText(self.current_selected_speed_name)
        self.speed_combo.currentTextChanged.connect(self.on_speed_changed)
        toolbar.addWidget(self.speed_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Voice: "))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(list(self.voice_models.keys()))
        self.voice_combo.setCurrentText(self.current_selected_voice_name) # Voz padrão
        self.voice_combo.currentTextChanged.connect(self.on_voice_changed)
        toolbar.addWidget(self.voice_combo)

    def get_current_speed_scale(self):
        if self.current_selected_speed_name == "Random":
            # Pega todas as escalas de velocidade reais, excluindo a opção "Random"
            actual_speed_scales = [scale for name, scale in self.speed_options.items() if name != "Random"]
            return random.choice(actual_speed_scales) if actual_speed_scales else 1.0 # Fallback para normal
        return self.speed_options.get(self.current_selected_speed_name, 1.0) # Fallback para normal


    def on_speed_changed(self, text_value):
        self.current_selected_speed_name = text_value
        print(f"Speed selection changed to: {text_value}")

    def on_voice_changed(self, voice_name):
        self.current_selected_voice_name = voice_name
        print(f"Voice selection changed to: {voice_name}")
        # Não alteramos mais piper_worker.model_onnx diretamente aqui
        # A obtenção do modelo efetivo será feita em get_effective_voice_model_path

    def get_effective_voice_model_path(self):
        if self.current_selected_voice_name == "Random":
            # Pega todos os caminhos de modelo reais, excluindo a opção "Random"
            actual_model_paths = [path for name, path in self.voice_models.items() if name != "Random"]
            if not actual_model_paths:
                print("Error: No actual voices available for random selection.")
                return CAMINHO_MODELO_VOZ_ONNX_DEFAULT # Fallback
            return random.choice(actual_model_paths)
        
        selected_path = self.voice_models.get(self.current_selected_voice_name)
        if not selected_path:
            print(f"Error: Voice name '{self.current_selected_voice_name}' not found in models. Using default.")
            return CAMINHO_MODELO_VOZ_ONNX_DEFAULT # Fallback
        return selected_path

    def update_student_level(self, correct_streak_ended=False):
        if correct_streak_ended:
            self.consecutive_correct_answers = 0
        else:
            self.consecutive_correct_answers += 1

        new_level_name = "Noob" # Padrão atualizado
        # Itera sobre os níveis em ordem decrescente de acertos necessários
        for threshold, name in sorted(self.student_levels.items(), reverse=True):
            if self.consecutive_correct_answers >= threshold:
                new_level_name = name
                break
        
        if self.current_student_level_name != new_level_name:
            # Poderia tocar um som de "level up" aqui
            print(f"NEW LEVEL: {new_level_name}!") # Log new level before updating current
            self.current_student_level_name = new_level_name # Atualiza após a verificação para a mensagem de "NOVO NÍVEL"

        self.level_display_label.setText(f"Level: {self.current_student_level_name}")
        self.level_display_label.setStyleSheet(f"color: {self.student_level_colors[self.current_student_level_name]}; padding: 10px; font-size: 24pt; font-weight: bold;")
        self._apply_level_style_to_tabs()

    def _apply_level_style_to_tabs(self):
        level_color = self.student_level_colors.get(self.current_student_level_name, "grey") # Cor padrão
        
        # Define a cor do texto da aba selecionada para contraste
        # Se a cor do nível for clara (como amarelo), texto escuro. Se for escura, texto claro.
        # Esta é uma heurística simples, pode precisar de ajuste.
        selected_tab_text_color = "black" if level_color in ["GoldenRod", "orange"] else "white" # Updated Hacker color
        if level_color == "grey": # Cinza pode ser médio
            selected_tab_text_color = "black"

        tab_style_sheet = f"""
            QTabWidget::pane {{
                border: 3px solid {level_color};
                border-radius: 5px;
                margin-top: -1px; /* Ajusta o alinhamento da borda com a barra de abas */
            }}
            QTabBar::tab:selected {{
                background-color: {level_color};
                color: {selected_tab_text_color};
                border: 1px solid {level_color}; /* Borda da aba para consistência */
                border-bottom-color: {level_color}; /* Para fundir com o pane */
            }}
            QTabBar::tab:!selected {{
                background-color: #E0E0E0; /* Cor de fundo para abas não selecionadas */
                color: black;
                border: 1px solid #C0C0C0;
                border-bottom-color: #C0C0C0;
            }}
            QTabBar::tab {{
                padding: 8px; /* Espaçamento interno das abas */
                min-width: 100px; /* Largura mínima para cada aba */
            }}
        """
        self.tab_widget.setStyleSheet(tab_style_sheet)

    def import_word_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Word File", self.WORDLISTS_DIR_NAME, "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            success, message = self.word_manager.load_words_from_file(file_path)
            if success:
                self.current_word_file_path = file_path # Armazena o caminho do arquivo carregado
                QMessageBox.information(self, "Success", message)
                self.reset_progress_action.setEnabled(True) # Habilita a opção de resetar

                # Verificar e carregar progresso
                self._handle_progress_loading()
                
                # Atualizar UI das abas
                self._refresh_tabs_after_load()
            else:
                QMessageBox.critical(self, "Error", message)
                self.current_word_file_path = None
                self.reset_progress_action.setEnabled(False)

    def _get_progress_file_path(self, word_file_path):
        if not word_file_path:
            return None
        # Cria o nome do arquivo de progresso oculto dentro do diretório wordlists
        base_filename = os.path.basename(word_file_path)
        progress_filename = f".{base_filename}.progress.json"
        return os.path.join(self.WORDLISTS_DIR_NAME, progress_filename)

    def _handle_progress_loading(self):
        progress_file = self._get_progress_file_path(self.current_word_file_path)
        load_new = True # Por padrão, começa do zero

        if progress_file and os.path.exists(progress_file):
            reply = QMessageBox.question(self, "Load Progress",
                                         "Previous progress found for this word file.\n"
                                         "Do you want to continue where you left off?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        saved_state = json.load(f)
                    
                    self.word_manager.load_progress_data(saved_state.get("words_data", []))
                    self.consecutive_correct_answers = saved_state.get("consecutive_correct_answers", 0)
                    # O nível será atualizado por update_student_level
                    self.update_student_level() # Update based on loaded correct answers
                    QMessageBox.information(self, "Progress Loaded", "Your previous progress has been loaded.")
                    load_new = False
                except Exception as e:
                    QMessageBox.warning(self, "Error Loading Progress",
                                        f"Could not load progress: {e}\nStarting from scratch.")
        
        if load_new: # Se não carregou progresso ou usuário escolheu não carregar
            self.update_student_level(correct_streak_ended=True) # Reseta o nível

    def _refresh_tabs_after_load(self):
        """Atualiza a UI das abas após carregar um arquivo (com ou sem progresso)."""
        self.dictation_tab.current_word_text = None
        self.dictation_tab.update_ui_for_new_word()
        self.dictation_tab.update_stats_summary()
        self.dictation_tab.show_feedback("File loaded. Click '▶️ Speak Word' to begin.")

        self.spelling_tab.current_word_text = None
        self.spelling_tab.update_ui_for_new_word()
        self.spelling_tab.update_stats_summary()
        self.spelling_tab.show_feedback("File loaded. Click '▶️ Spell Word' to begin.")

    def save_current_progress(self):
        if not self.current_word_file_path or not self.word_manager.words_data:
            return # Nada para salvar

        progress_file = self._get_progress_file_path(self.current_word_file_path)
        if not progress_file: return

        # Garante que o diretório wordlists existe antes de salvar
        os.makedirs(os.path.dirname(progress_file), exist_ok=True)

        data_to_save = {
            "words_data": self.word_manager.get_progress_data_to_save(),
            "consecutive_correct_answers": self.consecutive_correct_answers,
            # "current_student_level_name": self.current_student_level_name # O nível é derivado
        }
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            print(f"Progress saved to: {progress_file}")
        except Exception as e:
            print(f"Error saving progress: {e}")
            QMessageBox.warning(self, "Error Saving", f"Could not save progress: {e}")


    def closeEvent(self, event):
        # Exibir estatísticas antes de fechar
        reply = QMessageBox.question(self, 'Exit',
                                     "Are you sure you want to exit?\n\nSession Statistics:\n" +
                                     self.word_manager.get_full_stats(),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.save_current_progress() # Salva o progresso antes de sair
            # Parar o thread do TTS
            if self.tts_thread.isRunning():
                self.tts_thread.quit()
                self.tts_thread.wait(5000) # Espera até 5 segundos pelo thread terminar
            event.accept()
        else:
            event.ignore()
    
    def reset_current_progress_dialog(self):
        if not self.current_word_file_path or not self.word_manager.words_data:
            QMessageBox.information(self, "Reset Progress", "No word file loaded to reset.")
            return

        reply = QMessageBox.question(self, "Reset Progress",
                                     "Are you sure you want to reset all progress for the current word file?\n"
                                     "This will erase your correct answers, errors, and mastered words.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.word_manager.reset_all_word_stats()
            self.update_student_level(correct_streak_ended=True) # Reseta o nível do aluno
            
            progress_file = self._get_progress_file_path(self.current_word_file_path)
            if progress_file and os.path.exists(progress_file):
                try:
                    os.remove(progress_file)
                    print(f"Progress file '{progress_file}' removed.")
                except OSError as e:
                    print(f"Could not remove progress file '{progress_file}': {e}")
            
            self._refresh_tabs_after_load() # Atualiza a UI das abas
            QMessageBox.information(self, "Progress Reset", "The progress has been reset.")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Você pode definir um estilo global aqui, se desejar
    # app.setStyle("Fusion") 
    main_window = MainWindow()
    sys.exit(app.exec())
