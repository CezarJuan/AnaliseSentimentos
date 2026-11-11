"""CLI: `sentimento "texto"` ou JSONL pela stdin -> JSONL na stdout.

`sentimento serve [--porta N] [--modelo DIR]` sobe a interface web local.
Para analisar a palavra literal "serve", use `sentimento -- serve`.

Códigos de saída: 0 ok; 1 alguma linha JSONL inválida; 2 erro de uso ou de artefatos.
"""

from __future__ import annotations

import argparse
import json
import sys

from .analisador import Analisador, ErroArtefato


def _configurar_utf8() -> None:
    # No Windows o console usa cp1252/cp850 por padrão; "-sig" descarta BOM na entrada.
    for fluxo, codificacao in ((sys.stdin, "utf-8-sig"), (sys.stdout, "utf-8"), (sys.stderr, "utf-8")):
        reconfigure = getattr(fluxo, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding=codificacao)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sentimento",
        description="Analisa sentimento de textos em PT-BR. Sem TEXTO, lê JSONL da entrada padrão "
        '(uma linha por objeto: {"texto": "...", "id": opcional}).',
        epilog='Interface web: "sentimento serve [--porta N]". Para analisar a palavra "serve", '
        'use "sentimento -- serve".',
    )
    p.add_argument("texto", nargs="?", help="texto a analisar")
    p.add_argument("--explicar", action="store_true", help="inclui os tokens de maior peso")
    p.add_argument("--modelo", metavar="DIR", help="diretório de artefatos (padrão: embutidos)")
    p.add_argument("--versao", action="store_true", help="imprime a versão dos artefatos e sai")
    return p


def _emitir(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _processar_jsonl(analisador: Analisador, explicar: bool) -> int:
    houve_erro = False
    for n, linha in enumerate(sys.stdin, start=1):
        if not linha.strip():
            continue
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError as e:
            _emitir({"linha": n, "erro": f"JSON inválido: {e.msg}"})
            houve_erro = True
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("texto"), str):
            saida = {"linha": n, "erro": "campo 'texto' (string) ausente"}
            if isinstance(obj, dict) and "id" in obj:
                saida = {"id": obj["id"], **saida}
            _emitir(saida)
            houve_erro = True
            continue
        resultado = analisador.analisar(obj["texto"], explicar=explicar)
        _emitir({"id": obj["id"], **resultado} if "id" in obj else resultado)
    return 1 if houve_erro else 0


def _serve(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="sentimento serve", description="Sobe a interface web local em 127.0.0.1.")
    p.add_argument("--porta", type=int, default=8080, help="porta TCP (padrão: 8080)")
    p.add_argument("--modelo", metavar="DIR", help="diretório de artefatos (padrão: embutidos)")
    args = p.parse_args(argv)

    from .servidor import criar_servidor  # import tardio: a CLI de texto não paga o custo

    try:
        analisador = Analisador.carregar(args.modelo)
    except ErroArtefato as e:
        print(f"sentimento: erro: {e}", file=sys.stderr)
        return 2
    try:
        servidor = criar_servidor(analisador, args.porta)
    except (OSError, OverflowError) as e:
        motivo = getattr(e, "strerror", None) or str(e)
        print(f"sentimento: erro: não foi possível usar a porta {args.porta} ({motivo}); tente --porta", file=sys.stderr)
        return 2

    if sys.platform == "win32":
        import signal

        # Ctrl+Break também encerra de forma limpa (Ctrl+C já gera KeyboardInterrupt).
        def _interromper(*_):
            raise KeyboardInterrupt

        signal.signal(signal.SIGBREAK, _interromper)

    print(f"Interface em {servidor.url}  (Ctrl+C para encerrar)", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    print("Servidor encerrado.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    _configurar_utf8()
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["serve"]:
        return _serve(argv[1:])
    args = _parser().parse_args(argv)
    try:
        analisador = Analisador.carregar(args.modelo)
    except ErroArtefato as e:
        print(f"sentimento: erro: {e}", file=sys.stderr)
        return 2

    if args.versao:
        print(analisador.versao)
        return 0
    if args.texto is not None:
        _emitir(analisador.analisar(args.texto, explicar=args.explicar))
        return 0
    return _processar_jsonl(analisador, args.explicar)
