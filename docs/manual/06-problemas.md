# 6. Perguntas frequentes e solução de problemas

**"ngspice não encontrado" no canto da tela.** No pacote do Windows isso não deve ocorrer. Na
instalação pelo código-fonte, defina `CIRCUITOS_NGSPICE_EXE` e `CIRCUITOS_NGSPICE_LIB`. No
Windows, a pasta da DLL precisa de `sndfile.dll` e `samplerate.dll` (vêm na pasta `bin` do
pacote do executável do ngspice 47).

**"Memória insuficiente para guardar os resultados da simulação".** O ngspice estima a memória da
saída antes de começar. Reduza o tempo simulado, aumente o passo de saída de `.tran`, use TSTART
para guardar só o regime permanente ou salve só os vetores necessários (`.save`).

**"Passo de tempo muito pequeno" / "matriz singular".** A mensagem traz sugestões: passo máximo
em `.tran`, tempos de subida não nulos, resistência de alto valor para nós flutuantes, `.ic`.

**O projeto diz "nenhum componente liberado atende às margens".** Libere componentes na revisão
(aba Componentes) ou trave um componente à mão. O cálculo segue com dispositivos ideais e avisa.

**A importação de datasheet achou pouco.** O mapeamento por regras depende das tabelas em linhas.
Use **+ valor manual**, ou o modelo de linguagem se houver chave. Valores ausentes custam
digitação; valores errados custam revisão, e por isso a importação é conservadora.

**O relatório em PDF mostra uma equação como código LaTeX.** O gerador de PDF não reconheceu
aquela notação; ela aparece como fonte para não sumir. A versão HTML (KaTeX) mostra a equação.

**Porta 8000 em uso.** Feche a outra cópia do programa ou use `--port 8001`.

**Antivírus bloqueou `Ohmnia.exe`.** Executáveis novos sem assinatura digital às vezes são
bloqueados; libere a pasta do programa.
