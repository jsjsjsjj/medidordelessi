import tkinter as tk
from tkinter import ttk, font, filedialog
import random
import math
import winsound
import colorsys
import os
import threading
import ctypes
import queue

# ─── Constantes ──────────────────────────────────────────────────────────────
MAX_LESSI        = 1_000_000_000
LIMITE_ALERTA    = 500_000_000
COR_FUNDO        = "#0d0d1a"
COR_PAINEL       = "#13132b"
COR_BORDA        = "#2a2a5a"
COR_ACCENT       = "#7f5af0"
COR_ACCENT2      = "#2cb67d"
COR_ALERTA       = "#ff4466"
COR_TEXTO        = "#fffffe"
COR_SUBTEXT      = "#94a1b2"
COR_NAO_LESSI    = "#2cb67d"
CANVAS_W         = 500
CANVAS_H         = 500
RAIO             = 190
CX               = CANVAS_W // 2
CY               = CANVAS_H // 2


def lessi_to_cor(valor: int) -> str:
    """Interpola de verde → amarelo → vermelho baseado no valor."""
    t = valor / MAX_LESSI
    if t < 0.1:
        r, g, b = 0x2c, 0xb6, 0x7d
    elif t < 0.5:
        frac = (t - 0.1) / 0.4
        r = int(0x2c + (0xff - 0x2c) * frac)
        g = int(0xb6 + (0xcc - 0xb6) * frac)
        b = int(0x7d * (1 - frac))
    else:
        frac = (t - 0.5) / 0.5
        r = int(0xff)
        g = int(0xcc * (1 - frac))
        b = 0
    return f"#{r:02x}{g:02x}{b:02x}"


def formatar_lessi(v: int) -> str:
    if v >= 1_000_000_000:
        return "1 bilhão"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return str(v)


class MedidorLessi(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Medidor de Lessi ™")
        self.configure(bg=COR_FUNDO)
        self.resizable(False, False)

        # Estado
        self._valor_atual  = 0
        self._valor_alvo   = 0
        self._animando     = False
        self._nome_atual   = "???"
        self._alerta_ativo = False
        self._arquivo_som  = None   # None = usa o padrão do Windows
        self._som_pausado  = False  # controle de pausa MCI
        self._mci_queue    = queue.Queue()  # comandos para a thread MCI

        self._build_ui()
        self._desenhar_fundo()
        self._atualizar_ponteiro(0)
        self.mainloop()

    # ─── Construção da UI ─────────────────────────────────────────────────
    def _build_ui(self):
        # Título
        tk.Label(
            self, text="⚡ MEDIDOR DE LESSI ⚡",
            bg=COR_FUNDO, fg=COR_ACCENT,
            font=("Consolas", 20, "bold"), pady=10
        ).pack()

        # Canvas do medidor
        self._canvas = tk.Canvas(
            self, width=CANVAS_W, height=CANVAS_H,
            bg=COR_FUNDO, highlightthickness=0
        )
        self._canvas.pack(padx=20)

        # Painel de controles
        painel = tk.Frame(self, bg=COR_PAINEL, bd=0, pady=14, padx=20)
        painel.pack(fill="x", padx=20, pady=(0, 6))

        # Nome
        tk.Label(painel, text="Nome:", bg=COR_PAINEL, fg=COR_SUBTEXT,
                 font=("Consolas", 11)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._entry_nome = tk.Entry(
            painel, font=("Consolas", 12), width=20,
            bg="#1e1e3f", fg=COR_TEXTO, insertbackground=COR_ACCENT,
            relief="flat", bd=4
        )
        self._entry_nome.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self._entry_nome.insert(0, "Patrick")

        # Valor
        tk.Label(painel, text="Lessi:", bg=COR_PAINEL, fg=COR_SUBTEXT,
                 font=("Consolas", 11)).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._entry_valor = tk.Entry(
            painel, font=("Consolas", 12), width=20,
            bg="#1e1e3f", fg=COR_TEXTO, insertbackground=COR_ACCENT,
            relief="flat", bd=4
        )
        self._entry_valor.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))
        self._entry_valor.insert(0, "0")

        # Slider
        tk.Label(painel, text="Ajuste:", bg=COR_PAINEL, fg=COR_SUBTEXT,
                 font=("Consolas", 11)).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._slider_var = tk.IntVar(value=0)
        self._slider = ttk.Scale(
            painel, from_=0, to=MAX_LESSI,
            orient="horizontal", variable=self._slider_var,
            command=self._slider_moved
        )
        self._slider.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))

        painel.columnconfigure(1, weight=1)

        # Botões principais
        btn_frame = tk.Frame(self, bg=COR_FUNDO)
        btn_frame.pack(pady=10)

        self._btn_medir = self._make_btn(btn_frame, "📊  MEDIR", COR_ACCENT, self._medir_manual)
        self._btn_medir.pack(side="left", padx=8)

        self._btn_random = self._make_btn(btn_frame, "🎲  ALEATÓRIO", COR_ACCENT2, self._medir_aleatorio)
        self._btn_random.pack(side="left", padx=8)

        self._btn_reset = self._make_btn(btn_frame, "↺  RESET", "#444466", self._reset)
        self._btn_reset.pack(side="left", padx=8)

        # Label de status (alerta vermelho OU aviso verde)
        self._label_alerta = tk.Label(
            self, text="", bg=COR_FUNDO, fg=COR_ALERTA,
            font=("Consolas", 15, "bold"), pady=4
        )
        self._label_alerta.pack()

        # ── Painel de Som ──────────────────────────────────────────────────
        painel_som = tk.Frame(self, bg=COR_PAINEL, bd=0, pady=10, padx=20)
        painel_som.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(painel_som, text="🔊 Som do alerta:", bg=COR_PAINEL, fg=COR_SUBTEXT,
                 font=("Consolas", 10, "bold")).grid(row=0, column=0, columnspan=4,
                 sticky="w", pady=(0, 6))

        self._label_som = tk.Label(
            painel_som, text="⬦  Padrão do Windows",
            bg="#1e1e3f", fg=COR_SUBTEXT,
            font=("Consolas", 9), anchor="w", padx=8,
            relief="flat", width=28
        )
        self._label_som.grid(row=1, column=0, sticky="ew", padx=(0, 6))

        self._btn_escolher_som = tk.Button(
            painel_som, text="📂  Escolher",
            command=self._escolher_som,
            bg=COR_ACCENT, fg=COR_TEXTO, activebackground=COR_ACCENT,
            font=("Consolas", 9, "bold"),
            relief="flat", bd=0, padx=10, pady=5, cursor="hand2"
        )
        self._btn_escolher_som.grid(row=1, column=1, padx=(0, 6))

        self._btn_pausar_som = tk.Button(
            painel_som, text="⏸  Pausar",
            command=self._pausar_som,
            bg="#1a6b4a", fg=COR_TEXTO, activebackground="#1a6b4a",
            font=("Consolas", 9, "bold"),
            relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
            state="disabled"
        )
        self._btn_pausar_som.grid(row=1, column=2, padx=(0, 6))

        self._btn_remover_som = tk.Button(
            painel_som, text="✕  Padrão",
            command=self._remover_som,
            bg="#333355", fg=COR_SUBTEXT, activebackground="#444466",
            font=("Consolas", 9),
            relief="flat", bd=0, padx=10, pady=5, cursor="hand2"
        )
        self._btn_remover_som.grid(row=1, column=3)

        painel_som.columnconfigure(0, weight=1)

    def _make_btn(self, parent, texto, cor, cmd):
        return tk.Button(
            parent, text=texto, command=cmd,
            bg=cor, fg=COR_TEXTO, activebackground=cor,
            font=("Consolas", 11, "bold"),
            relief="flat", bd=0, padx=16, pady=8, cursor="hand2"
        )

    # ─── Desenho do medidor ───────────────────────────────────────────────
    def _desenhar_fundo(self):
        c = self._canvas
        c.delete("fundo")

        c.create_arc(
            CX - RAIO, CY - RAIO, CX + RAIO, CY + RAIO,
            start=210, extent=-240,
            style="arc", outline="#222244", width=22,
            tags="fundo"
        )

        # Marcas (ticks)
        for i in range(11):
            ang_deg = 210 - i * 24
            ang_rad = math.radians(ang_deg)
            r_outer = RAIO - 4
            r_inner = RAIO - (22 if i % 5 == 0 else 12)
            x1 = CX + r_outer * math.cos(ang_rad)
            y1 = CY - r_outer * math.sin(ang_rad)
            x2 = CX + r_inner * math.cos(ang_rad)
            y2 = CY - r_inner * math.sin(ang_rad)
            c.create_line(x1, y1, x2, y2, fill="#333366", width=2 if i % 5 == 0 else 1, tags="fundo")

        # Rótulos de escala
        labels = ["0", "100M", "200M", "300M", "400M", "500M",
                  "600M", "700M", "800M", "900M", "1B"]
        for i, lbl in enumerate(labels):
            ang_deg = 210 - i * 24
            ang_rad = math.radians(ang_deg)
            rx = CX + (RAIO - 40) * math.cos(ang_rad)
            ry = CY - (RAIO - 40) * math.sin(ang_rad)
            c.create_text(rx, ry, text=lbl, fill=COR_SUBTEXT,
                          font=("Consolas", 7), tags="fundo")

        # Linha de alerta (500M)
        ang_alerta = math.radians(210 - (LIMITE_ALERTA / MAX_LESSI) * 240)
        r1, r2 = RAIO - 4, RAIO + 8
        c.create_line(
            CX + r1 * math.cos(ang_alerta), CY - r1 * math.sin(ang_alerta),
            CX + r2 * math.cos(ang_alerta), CY - r2 * math.sin(ang_alerta),
            fill=COR_ALERTA, width=3, tags="fundo"
        )
        c.create_text(
            CX + (RAIO + 22) * math.cos(ang_alerta),
            CY - (RAIO + 22) * math.sin(ang_alerta),
            text="⚠", fill=COR_ALERTA, font=("Consolas", 10), tags="fundo"
        )

    def _atualizar_ponteiro(self, valor: int):
        c = self._canvas
        c.delete("ponteiro")
        c.delete("centro")
        c.delete("valor_txt")
        c.delete("nome_txt")
        c.delete("arco_vivo")

        cor = lessi_to_cor(valor)
        frac = valor / MAX_LESSI
        ang_deg = 210 - frac * 240
        ang_rad = math.radians(ang_deg)

        # Arco "preenchido"
        extent_arc = -frac * 240
        if abs(extent_arc) > 0.5:
            c.create_arc(
                CX - RAIO, CY - RAIO, CX + RAIO, CY + RAIO,
                start=210, extent=extent_arc,
                style="arc", outline=cor, width=18,
                tags="arco_vivo"
            )

        # Ponteiro
        comprimento = RAIO - 28
        xp = CX + comprimento * math.cos(ang_rad)
        yp = CY - comprimento * math.sin(ang_rad)
        c.create_line(CX, CY, xp, yp, fill=cor, width=4,
                      capstyle="round", tags="ponteiro")

        # Ponta brilhante
        c.create_oval(xp - 6, yp - 6, xp + 6, yp + 6,
                      fill=cor, outline="", tags="ponteiro")

        # Centro
        c.create_oval(CX - 12, CY - 12, CX + 12, CY + 12,
                      fill=COR_ACCENT, outline="", tags="centro")

        # Texto do valor
        c.create_text(CX, CY + 55, text=formatar_lessi(valor),
                      fill=cor, font=("Consolas", 22, "bold"),
                      tags="valor_txt")

        # Nome
        nome = self._nome_atual
        c.create_text(CX, CY + 90, text=nome,
                      fill=COR_SUBTEXT, font=("Consolas", 13),
                      tags="nome_txt")

    # ─── Animação ─────────────────────────────────────────────────────────
    def _animar(self):
        if not self._animando:
            return
        diff = self._valor_alvo - self._valor_atual
        if abs(diff) < 500:
            self._valor_atual = self._valor_alvo
            self._animando = False
            self._atualizar_ponteiro(self._valor_atual)
            self._verificar_alerta(self._valor_atual)
            return
        self._valor_atual += int(diff * 0.08)
        self._atualizar_ponteiro(self._valor_atual)
        self.after(16, self._animar)

    def _iniciar_animacao(self, alvo: int, nome: str):
        self._nome_atual = nome
        self._valor_alvo = max(0, min(MAX_LESSI, alvo))
        self._animando = True
        self._label_alerta.config(text="")
        self._alerta_ativo = False
        self._animar()

    # ─── Som ──────────────────────────────────────────────────────────────
    def _escolher_som(self):
        caminho = filedialog.askopenfilename(
            title="Escolher efeito sonoro",
            filetypes=[
                ("Arquivos de áudio", "*.wav *.mp3 *.ogg"),
                ("WAV", "*.wav"),
                ("Todos os arquivos", "*.*"),
            ]
        )
        if caminho:
            self._arquivo_som = caminho
            nome_curto = os.path.basename(caminho)
            if len(nome_curto) > 26:
                nome_curto = "…" + nome_curto[-24:]
            self._label_som.config(text=f"♪  {nome_curto}", fg=COR_ACCENT2)

    def _remover_som(self):
        self._mci_queue.put("stop")
        self._arquivo_som = None
        self._som_pausado = False
        self._label_som.config(text="⬦  Padrão do Windows", fg=COR_SUBTEXT)
        self._btn_pausar_som.config(state="disabled", text="⏸  Pausar")

    def _pausar_som(self):
        """Envia pause/resume para a thread MCI via fila."""
        if not self._som_pausado:
            self._mci_queue.put("pause")
            self._som_pausado = True
            self._btn_pausar_som.config(text="▶  Retomar")
        else:
            self._mci_queue.put("resume")
            self._som_pausado = False
            self._btn_pausar_som.config(text="⏸  Pausar")

    def _tocar_alerta(self):
        def _play():
            try:
                if self._arquivo_som and os.path.isfile(self._arquivo_som):
                    ext = os.path.splitext(self._arquivo_som)[1].lower()
                    if ext == ".wav":
                        winsound.PlaySound(self._arquivo_som,
                                           winsound.SND_FILENAME | winsound.SND_ASYNC)
                    else:
                        self._tocar_mci(self._arquivo_som)
                else:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        threading.Thread(target=_play, daemon=True).start()

    def _tocar_mci(self, caminho: str):
        """Abre sessão MCI na thread atual e processa comandos via fila.
        Pause/resume/stop são enviados pela thread principal via _mci_queue."""
        import time
        mci = ctypes.windll.winmm.mciSendStringW
        buf = ctypes.create_unicode_buffer(64)

        # Limpa fila de comandos anteriores
        while not self._mci_queue.empty():
            try:
                self._mci_queue.get_nowait()
            except queue.Empty:
                break

        # Abre o arquivo nesta thread
        ret = mci(f'open "{caminho}" alias lessi_som', None, 0, 0)
        if ret != 0:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return

        mci('play lessi_som', None, 0, 0)
        self._som_pausado = False
        self.after(0, lambda: self._btn_pausar_som.config(state="normal", text="⏸  Pausar"))

        # Loop: processa comandos e monitora fim do áudio — tudo na mesma thread
        while True:
            # Drena comandos pendentes
            try:
                cmd = self._mci_queue.get_nowait()
                if cmd == "pause":
                    mci("pause lessi_som", None, 0, 0)
                elif cmd == "resume":
                    mci("resume lessi_som", None, 0, 0)
                elif cmd == "stop":
                    mci("stop lessi_som", None, 0, 0)
                    mci("close lessi_som", None, 0, 0)
                    self.after(0, lambda: self._btn_pausar_som.config(
                        state="disabled", text="⏸  Pausar"))
                    return
            except queue.Empty:
                pass

            # Verifica se o áudio terminou
            err = mci("status lessi_som mode", buf, 64, 0)
            if err != 0:
                break
            if buf.value.strip() == "stopped":
                mci("close lessi_som", None, 0, 0)
                self.after(0, lambda: self._btn_pausar_som.config(
                    state="disabled", text="⏸  Pausar"))
                break

            time.sleep(0.05)

    # ─── Alerta ───────────────────────────────────────────────────────────
    def _verificar_alerta(self, valor: int):
        nome = self._nome_atual
        if valor > LIMITE_ALERTA:
            if not self._alerta_ativo:
                self._alerta_ativo = True
                self._label_alerta.config(text=f"⚠  O {nome} é muito lessi!  ⚠", fg=COR_ALERTA)
                self._piscar_alerta(6)
                self._tocar_alerta()
        else:
            # Valor abaixo do limite → pessoa não é lessi
            self._label_alerta.config(
                text=f"✔  {nome} não é lessi!",
                fg=COR_NAO_LESSI
            )
            self._alerta_ativo = False

    def _piscar_alerta(self, n: int):
        if n <= 0:
            self._label_alerta.config(fg=COR_ALERTA)
            return
        cor = COR_ALERTA if n % 2 == 0 else COR_FUNDO
        self._label_alerta.config(fg=cor)
        self.after(200, lambda: self._piscar_alerta(n - 1))

    # ─── Ações dos botões ─────────────────────────────────────────────────
    def _medir_manual(self):
        nome = self._entry_nome.get().strip() or "???"
        try:
            v = int(self._entry_valor.get().replace(".", "").replace(",", ""))
        except ValueError:
            self._entry_valor.delete(0, "end")
            self._entry_valor.insert(0, "0")
            v = 0
        self._slider_var.set(v)
        self._iniciar_animacao(v, nome)

    def _medir_aleatorio(self):
        nome = self._entry_nome.get().strip() or "???"
        v = random.randint(0, MAX_LESSI)
        self._entry_valor.delete(0, "end")
        self._entry_valor.insert(0, str(v))
        self._slider_var.set(v)
        self._iniciar_animacao(v, nome)

    def _slider_moved(self, val):
        v = int(float(val))
        self._entry_valor.delete(0, "end")
        self._entry_valor.insert(0, str(v))
        nome = self._entry_nome.get().strip() or "???"
        self._nome_atual = nome
        self._valor_atual = v
        self._valor_alvo  = v
        self._animando    = False
        self._atualizar_ponteiro(v)
        if v <= LIMITE_ALERTA:
            self._alerta_ativo = False
        self._verificar_alerta(v)

    def _reset(self):
        self._entry_valor.delete(0, "end")
        self._entry_valor.insert(0, "0")
        self._slider_var.set(0)
        self._label_alerta.config(text="")
        self._alerta_ativo = False
        self._iniciar_animacao(0, self._nome_atual)


if __name__ == "__main__":
    MedidorLessi()
