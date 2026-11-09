from mediateca.catalog.parser import parse_detail, parse_file, parse_search_results


def test_parsea_dvd(dvd_fixture) -> None:
    parsed = parse_file(str(dvd_fixture))

    assert parsed.titn == "2101557"
    assert parsed.titulo.startswith("20.000 especies de abejas")
    assert parsed.anio == 2023
    assert parsed.duracion_min == 129
    assert parsed.idioma == "spa"
    assert parsed.pais == "sp"
    assert parsed.ean == "8436587701627"
    assert parsed.soportes == ["DVD"]
    assert "Dramas cinematográficos" in parsed.generos
    assert "Cine español" in parsed.materias
    assert len(parsed.enlaces) == 2


def test_parser_extrae_personas_y_roles(dvd_fixture) -> None:
    parsed = parse_file(str(dvd_fixture))
    roles = {role for persona in parsed.personas for role in persona.roles}
    nombres = {persona.nombre for persona in parsed.personas}

    assert "director de cine" in roles
    assert "guionista" in roles
    assert "actor" in roles
    assert "Urresola Solaguren, Estíbaliz" in nombres
    assert "Otero, Sofía (2013-)" in nombres


def test_parser_extrae_ejemplares(dvd_fixture) -> None:
    parsed = parse_file(str(dvd_fixture))

    assert len(parsed.ejemplares) == 2
    primero = parsed.ejemplares[0]
    assert primero.biblioteca_nombre.startswith("ALCALÁ DE HENARES")
    assert primero.sucursal_nombre == "B.P.M. Cardenal Cisneros"
    assert primero.signatura == "DVD-V 10879"
    assert primero.soporte == "DVD"
    assert not hasattr(primero, "disponible")
    assert not hasattr(primero, "estado")

    segundo = parsed.ejemplares[1]
    assert segundo.biblioteca_nombre.startswith("ALCORCÓN")
    assert segundo.signatura == "DVD-V 4421"
    assert segundo.soporte == "DVD"


def test_usa_enlace_permanente_del_opac() -> None:
    html = """
    <html><body>
      <span class="js-TITN">2101557</span>
      <span class="js-ntitl">Titulo de prueba</span>
      <span id="xslike">http://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac?TITN=2101557</span>
    </body></html>
    """

    parsed = parse_detail(html, url="https://opac/sesion?ACC=165&DOC=1")

    assert parsed.source_url == (
        "http://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac?TITN=2101557"
    )


def test_parsea_bluray(bluray_fixture) -> None:
    parsed = parse_file(str(bluray_fixture))

    assert parsed.titn == "2107423"
    assert parsed.soportes == ["Blu-ray"]
    assert parsed.duracion_min == 129
    assert parsed.ean == "8436587701634"
    assert len(parsed.ejemplares) == 1
    assert parsed.ejemplares[0].soporte == "Blu-ray"
    assert parsed.ejemplares[0].signatura == "BRD-00219"


def test_parsea_listado_de_resultados(search_results_fixture) -> None:
    html = search_results_fixture.read_text(encoding="utf-8")

    resultados = parse_search_results(html)

    assert len(resultados) == 3
    primero = resultados[0]
    assert primero.doc == 1
    assert primero.titn == "2101557"
    assert primero.titulo.startswith("20.000 especies de abejas")
    assert primero.anio == 2023
    assert primero.idioma == "spa"
    assert primero.descripcion_fisica.startswith("1 DVD-Video")
    assert primero.marc["T300a"].startswith("1 DVD-Video")
    assert primero.soportes == ["DVD"]
    assert "Dramas cinematográficos" in primero.generos
    assert "Cine español" in primero.materias
    assert primero.personas[0].nombre == "Urresola Solaguren, Estíbaliz"
    assert primero.personas[0].roles == ["director de cine"]

    assert resultados[1].titn == "2107423"
    assert resultados[1].soportes == ["Blu-ray"]
    assert resultados[1].ean == "8436587701634"

    assert resultados[2].titn == "2109999"
    assert resultados[2].anio == 1998
    assert resultados[2].soportes == ["VHS"]

