import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


WEB_URL = "https://www.prosegurcash.com/media/prensa"
BASE_URL = "https://www.prosegurcash.com"
ARCHIVO_RSS = Path("prosegur-cash.xml")

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def descargar_pagina():
    respuesta = requests.get(
        WEB_URL,
        headers=CABECERAS,
        timeout=60,
        allow_redirects=True,
    )
    respuesta.raise_for_status()

    if not respuesta.text.strip():
        raise RuntimeError("Prosegur Cash devolvió una página vacía")

    return respuesta.text


def buscar_contenedor(enlace):
    actual = enlace

    for _ in range(8):
        actual = actual.parent

        if actual is None:
            break

        texto = limpiar_texto(actual.get_text(" ", strip=True))

        if re.search(r"\b\d{2}/\d{2}/\d{4}\b", texto):
            if len(texto) <= 1500:
                return actual

    return enlace.parent


def obtener_titulo(enlace, contenedor):
    for etiqueta in ["h1", "h2", "h3", "h4", "h5"]:
        encabezado = contenedor.find(etiqueta)

        if encabezado:
            titulo = limpiar_texto(encabezado.get_text(" ", strip=True))

            if len(titulo) >= 15:
                return titulo

    titulo = limpiar_texto(enlace.get_text(" ", strip=True))

    titulo = re.sub(
        r"^Sala de Prensa\s+\d{2}/\d{2}/\d{4}\s*",
        "",
        titulo,
        flags=re.IGNORECASE,
    )

    return titulo


def obtener_descripcion(contenedor, titulo):
    texto = limpiar_texto(contenedor.get_text(" ", strip=True))

    texto = texto.replace(titulo, " ")
    texto = re.sub(
        r"\bSala de Prensa\b",
        " ",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", " ", texto)
    texto = limpiar_texto(texto)

    if texto == titulo:
        return ""

    return texto[:800]


def obtener_noticias(html):
    soup = BeautifulSoup(html, "html.parser")
    noticias = []
    enlaces_vistos = set()

    for enlace in soup.find_all("a", href=True):
        href = limpiar_texto(enlace.get("href"))

        if "/media/articulo/prensa/" not in href.lower():
            continue

        url = urljoin(BASE_URL, href)
        url = url.split("#")[0].split("?")[0]

        if url in enlaces_vistos:
            continue

        contenedor = buscar_contenedor(enlace)
        texto_contenedor = limpiar_texto(
            contenedor.get_text(" ", strip=True)
        )

        coincidencia_fecha = re.search(
            r"\b(\d{2}/\d{2}/\d{4})\b",
            texto_contenedor,
        )

        if not coincidencia_fecha:
            continue

        titulo = obtener_titulo(enlace, contenedor)

        if len(titulo) < 15:
            continue

        try:
            fecha = datetime.strptime(
                coincidencia_fecha.group(1),
                "%d/%m/%Y",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        descripcion = obtener_descripcion(contenedor, titulo)

        noticias.append(
            {
                "titulo": titulo,
                "url": url,
                "fecha": fecha,
                "descripcion": descripcion,
            }
        )

        enlaces_vistos.add(url)

    noticias.sort(
        key=lambda noticia: noticia["fecha"],
        reverse=True,
    )

    if not noticias:
        raise RuntimeError(
            "No se encontraron noticias en la Sala de Prensa "
            "de Prosegur Cash"
        )

    return noticias[:50]


def crear_rss(noticias):
    ahora = datetime.now(timezone.utc)

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        "<title>Prosegur Cash - Sala de Prensa</title>",
        f"<link>{escapar_xml(WEB_URL)}</link>",
        (
            "<description>Últimas noticias y comunicados "
            "oficiales de Prosegur Cash</description>"
        ),
        "<language>es</language>",
        f"<lastBuildDate>{format_datetime(ahora)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]

    for noticia in noticias:
        partes.extend(
            [
                "<item>",
                f"<title>{escapar_xml(noticia['titulo'])}</title>",
                f"<link>{escapar_xml(noticia['url'])}</link>",
                (
                    f"<guid isPermaLink=\"true\">"
                    f"{escapar_xml(noticia['url'])}</guid>"
                ),
                (
                    f"<pubDate>"
                    f"{format_datetime(noticia['fecha'])}"
                    f"</pubDate>"
                ),
                (
                    f"<description>"
                    f"{escapar_xml(noticia['descripcion'])}"
                    f"</description>"
                ),
                "</item>",
            ]
        )

    partes.extend(["</channel>", "</rss>"])

    return "\n".join(partes)


def escapar_xml(texto):
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def guardar_rss(contenido):
    temporal = ARCHIVO_RSS.with_suffix(".xml.tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(ARCHIVO_RSS)


def main():
    html = descargar_pagina()
    noticias = obtener_noticias(html)
    rss = crear_rss(noticias)
    guardar_rss(rss)

    print(
        f"RSS creada correctamente con {len(noticias)} noticias"
    )

    for noticia in noticias[:5]:
        print(
            noticia["fecha"].strftime("%d/%m/%Y"),
            "-",
            noticia["titulo"],
        )


if __name__ == "__main__":
    main()
