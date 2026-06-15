#!/usr/bin/env python3
"""Audit vocabulary coverage across all textbook lessons."""

import os
import re
import glob
import sys

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = r"c:\Users\OZI2SZH\_020 Project\_090 Other\_040 Python\New folder (2)\教材"

# Function words to exclude from checking
FUNCTION_WORDS = {
    # Articles
    'el', 'la', 'los', 'las', 'lo',
    'un', 'una', 'unos', 'unas',
    # Prepositions
    'a', 'de', 'en', 'con', 'por', 'para', 'sin', 'sobre', 'entre',
    'hacia', 'hasta', 'desde', 'según', 'durante', 'mediante', 'ante',
    'bajo', 'contra', 'tras', 'cabe',
    # Contractions
    'al', 'del',
    # Conjunctions
    'y', 'e', 'o', 'u', 'pero', 'que', 'si', 'porque', 'ni',
    'aunque', 'mientras', 'cuando', 'donde', 'como',
    # Personal pronouns (subject)
    'yo', 'tú', 'él', 'ella', 'usted',
    'nosotros', 'nosotras', 'vosotros', 'vosotras',
    'ellos', 'ellas', 'ustedes',
    # Object/reflexive pronouns
    'me', 'te', 'se', 'nos', 'os', 'lo', 'la', 'los', 'las', 'le', 'les',
    # Possessives (short forms - the ones that go before nouns)
    'mi', 'mis', 'tu', 'tus', 'su', 'sus',
    'nuestro', 'nuestra', 'nuestros', 'nuestras',
    'vuestro', 'vuestra', 'vuestros', 'vuestras',
    # Demonstratives
    'este', 'esta', 'esto', 'estos', 'estas',
    'ese', 'esa', 'eso', 'esos', 'esas',
    'aquel', 'aquella', 'aquello', 'aquellos', 'aquellas',
    # Interrogatives (also used as relative in some contexts)
    'qué', 'quién', 'quiénes', 'cuál', 'cuáles', 'cómo', 'cuándo',
    'dónde', 'adónde', 'cuánto', 'cuánta', 'cuántos', 'cuántas',
    'por qué',
    # Negation
    'no',
    # Common adverbs (function-like)
    'muy', 'más', 'menos', 'tan', 'tanto', 'tanta', 'tantos', 'tantas',
    'ya', 'ahora', 'entonces', 'también', 'tampoco', 'solo', 'sólo',
    'aquí', 'allí', 'ahí', 'allá', 'acá',
    # Common prepositions/conjunctions (extended)
    'pues', 'así', 'o sea',
    # Numbers 0-100 (basic)
    'cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete',
    'ocho', 'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince',
    'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte',
    'veintiuno', 'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco',
    'veintiséis', 'veintisiete', 'veintiocho', 'veintinueve', 'treinta',
    'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa',
    'cien', 'ciento',
    # Ordinals
    'primero', 'segundo', 'tercero', 'cuarto', 'quinto',
    'primer', 'tercer',
    # Common exclamations
    'hola', 'adiós', 'gracias', 'vale',
}

# Spanish verb conjugation patterns - common irregular forms -> infinitive
VERB_FORMS = {
    # ser
    'soy': 'ser', 'eres': 'ser', 'es': 'ser', 'somos': 'ser', 'sois': 'ser', 'son': 'ser',
    # estar
    'estoy': 'estar', 'estás': 'estar', 'está': 'estar', 'estamos': 'estar',
    'estáis': 'estar', 'están': 'estar',
    # tener
    'tengo': 'tener', 'tienes': 'tener', 'tiene': 'tener', 'tenemos': 'tener',
    'tenéis': 'tener', 'tienen': 'tener',
    # ir
    'voy': 'ir', 'vas': 'ir', 'va': 'ir', 'vamos': 'ir', 'vais': 'ir', 'van': 'ir',
    # hacer
    'hago': 'hacer', 'haces': 'hacer', 'hace': 'hacer', 'hacemos': 'hacer',
    'hacéis': 'hacer', 'hacen': 'hacer',
    # decir
    'digo': 'decir', 'dices': 'decir', 'dice': 'decir', 'decimos': 'decir',
    'decís': 'decir', 'dicen': 'decir',
    # venir
    'vengo': 'venir', 'vienes': 'venir', 'viene': 'venir', 'venimos': 'venir',
    'venís': 'venir', 'vienen': 'venir',
    # poder
    'puedo': 'poder', 'puedes': 'poder', 'puede': 'poder', 'podemos': 'poder',
    'podéis': 'poder', 'pueden': 'poder',
    # querer
    'quiero': 'querer', 'quieres': 'querer', 'quiere': 'querer', 'queremos': 'querer',
    'queréis': 'querer', 'quieren': 'querer',
    # saber
    'sé': 'saber', 'sabes': 'saber', 'sabe': 'saber', 'sabemos': 'saber',
    'sabéis': 'saber', 'saben': 'saber',
    # poner
    'pongo': 'poner', 'pones': 'poner', 'pone': 'poner', 'ponemos': 'poner',
    'ponéis': 'poner', 'ponen': 'poner',
    # dar
    'doy': 'dar', 'das': 'dar', 'da': 'dar', 'damos': 'dar', 'dais': 'dar', 'dan': 'dar',
    # ver
    'veo': 'ver', 'ves': 'ver', 've': 'ver', 'vemos': 'ver', 'veis': 'ver', 'ven': 'ver',
    # salir
    'salgo': 'salir', 'sales': 'salir', 'sale': 'salir', 'salimos': 'salir',
    'salís': 'salir', 'salen': 'salir',
    # traer
    'traigo': 'traer', 'traes': 'traer', 'trae': 'traer', 'traemos': 'traer',
    'traéis': 'traer', 'traen': 'traer',
    # oír
    'oigo': 'oír', 'oyes': 'oír', 'oye': 'oír', 'oímos': 'oír', 'oís': 'oír', 'oyen': 'oír',
    # conocer
    'conozco': 'conocer', 'conoces': 'conocer', 'conoce': 'conocer',
    'conocemos': 'conocer', 'conocéis': 'conocer', 'conocen': 'conocer',
    # pedir (e->i)
    'pido': 'pedir', 'pides': 'pedir', 'pide': 'pedir', 'pedimos': 'pedir',
    'pedís': 'pedir', 'piden': 'pedir',
    # dormir (o->ue)
    'duermo': 'dormir', 'duermes': 'dormir', 'duerme': 'dormir',
    'dormimos': 'dormir', 'dormís': 'dormir', 'duermen': 'dormir',
    # jugar (u->ue)
    'juego': 'jugar', 'juegas': 'jugar', 'juega': 'jugar', 'jugamos': 'jugar',
    'jugáis': 'jugar', 'juegan': 'jugar',
    # pensar (e->ie)
    'pienso': 'pensar', 'piensas': 'pensar', 'piensa': 'pensar',
    'pensamos': 'pensar', 'pensáis': 'pensar', 'piensan': 'pensar',
    # empezar (e->ie)
    'empiezo': 'empezar', 'empiezas': 'empezar', 'empieza': 'empezar',
    'empezamos': 'empezar', 'empezáis': 'empezar', 'empiezan': 'empezar',
    # volver (o->ue)
    'vuelvo': 'volver', 'vuelves': 'volver', 'vuelve': 'volver',
    'volvemos': 'volver', 'volvéis': 'volver', 'vuelven': 'volver',
    # encontrar (o->ue)
    'encuentro': 'encontrar', 'encuentras': 'encontrar', 'encuentra': 'encontrar',
    'encontramos': 'encontrar', 'encontráis': 'encontrar', 'encuentran': 'encontrar',
    # contar (o->ue)
    'cuento': 'contar', 'cuentas': 'contar', 'cuenta': 'contar',
    'contamos': 'contar', 'contáis': 'contar', 'cuentan': 'contar',
    # costar (o->ue)
    'cuesto': 'costar', 'cuestas': 'costar', 'cuesta': 'costar',
    'costamos': 'costar', 'costáis': 'costar', 'cuestan': 'costar',
    # entender (e->ie)
    'entiendo': 'entender', 'entiendes': 'entender', 'entiende': 'entender',
    'entendemos': 'entender', 'entendéis': 'entender', 'entienden': 'entender',
    # preferir (e->ie)
    'prefiero': 'preferir', 'prefieres': 'preferir', 'prefiere': 'preferir',
    'preferimos': 'preferir', 'preferís': 'preferir', 'prefieren': 'preferir',
    # sentir (e->ie)
    'siento': 'sentir', 'sientes': 'sentir', 'siente': 'sentir',
    'sentimos': 'sentir', 'sentís': 'sentir', 'sienten': 'sentir',
    # cerrar (e->ie)
    'cierro': 'cerrar', 'cierras': 'cerrar', 'cierra': 'cerrar',
    'cerramos': 'cerrar', 'cerráis': 'cerrar', 'cierran': 'cerrar',
    # perder (e->ie)
    'pierdo': 'perder', 'pierdes': 'perder', 'pierde': 'perder',
    'perdemos': 'perder', 'perdéis': 'perder', 'pierden': 'perder',
    # recordar (o->ue)
    'recuerdo': 'recordar', 'recuerdas': 'recordar', 'recuerda': 'recordar',
    'recordamos': 'recordar', 'recordáis': 'recordar', 'recuerdan': 'recordar',
    # morir (o->ue)
    'muero': 'morir', 'mueres': 'morir', 'muere': 'morir',
    'morimos': 'morir', 'morís': 'morir', 'mueren': 'morir',
    # llover (o->ue)
    'llueve': 'llover',
    # nevar (e->ie)
    'nieva': 'nevar',
    # haber
    'he': 'haber', 'has': 'haber', 'ha': 'haber', 'hemos': 'haber',
    'habéis': 'haber', 'han': 'haber',
    'hay': 'haber',
    # decir preterite
    'dije': 'decir', 'dijiste': 'decir', 'dijo': 'decir',
    'dijimos': 'decir', 'dijisteis': 'decir', 'dijeron': 'decir',
    # hacer preterite
    'hice': 'hacer', 'hiciste': 'hacer', 'hizo': 'hacer',
    'hicimos': 'hacer', 'hicisteis': 'hacer', 'hicieron': 'hacer',
    # tener preterite
    'tuve': 'tener', 'tuviste': 'tener', 'tuvo': 'tener',
    'tuvimos': 'tener', 'tuvisteis': 'tener', 'tuvieron': 'tener',
    # estar preterite
    'estuve': 'estar', 'estuviste': 'estar', 'estuvo': 'estar',
    'estuvimos': 'estar', 'estuvisteis': 'estar', 'estuvieron': 'estar',
    # poder preterite
    'pude': 'poder', 'pudiste': 'poder', 'pudo': 'poder',
    'pudimos': 'poder', 'pudisteis': 'poder', 'pudieron': 'poder',
    # poner preterite
    'puse': 'poner', 'pusiste': 'poner', 'puso': 'poner',
    'pusimos': 'poner', 'pusisteis': 'poner', 'pusieron': 'poner',
    # saber preterite
    'supe': 'saber', 'supiste': 'saber', 'supo': 'saber',
    'supimos': 'saber', 'supisteis': 'saber', 'supieron': 'saber',
    # venir preterite
    'vine': 'venir', 'viniste': 'venir', 'vino': 'venir',
    'vinimos': 'venir', 'vinisteis': 'venir', 'vinieron': 'venir',
    # querer preterite
    'quise': 'querer', 'quisiste': 'querer', 'quiso': 'querer',
    'quisimos': 'querer', 'quisisteis': 'querer', 'quisieron': 'querer',
    # traer preterite
    'traje': 'traer', 'trajiste': 'traer', 'trajo': 'traer',
    'trajimos': 'traer', 'trajisteis': 'traer', 'trajeron': 'traer',
    # conducir preterite
    'conduje': 'conducir', 'condujiste': 'conducir', 'condujo': 'conducir',
    'condujimos': 'conducir', 'condujisteis': 'conducir', 'condujeron': 'conducir',
    # andar preterite
    'anduve': 'andar', 'anduviste': 'andar', 'anduvo': 'andar',
    'anduvimos': 'andar', 'anduvisteis': 'andar', 'anduvieron': 'andar',
    # dar preterite
    'di': 'dar', 'diste': 'dar', 'dio': 'dar', 'dimos': 'dar',
    'disteis': 'dar', 'dieron': 'dar',
    # ver preterite
    'vi': 'ver', 'viste': 'ver', 'vio': 'ver', 'vimos': 'ver',
    'visteis': 'ver', 'vieron': 'ver',
    # ser/ir preterite (same forms)
    'fui': 'ser', 'fuiste': 'ser', 'fue': 'ser', 'fuimos': 'ser',
    'fuisteis': 'ser', 'fueron': 'ser',
    # caber
    'quepo': 'caber', 'cabes': 'caber', 'cabe': 'caber', 'cabemos': 'caber',
    'cabéis': 'caber', 'caben': 'caber',
    # valer
    'valgo': 'valer', 'vales': 'valer', 'vale': 'valer',
    # caer
    'caigo': 'caer', 'caes': 'caer', 'cae': 'caer',
    # oler (o->hue)
    'huelo': 'oler', 'hueles': 'oler', 'huele': 'oler',
    # construir
    'construyo': 'construir', 'construyes': 'construir', 'construye': 'construir',
    # huir
    'huyo': 'huir', 'huyes': 'huir', 'huye': 'huir',
    # incluir
    'incluyo': 'incluir',
    # concluir
    'concluyo': 'concluir',
    # destruir
    'destruyo': 'destruir',
    # Common -ar present tense endings for detection
    # We handle these by pattern matching below
}

# Common irregular past participles
PAST_PARTICIPLES = {
    'hecho': 'hacer', 'dicho': 'decir', 'visto': 'ver', 'vuelto': 'volver',
    'puesto': 'poner', 'escrito': 'escribir', 'abierto': 'abrir',
    'muerto': 'morir', 'roto': 'romper', 'cubierto': 'cubrir',
    'resuelto': 'resolver', 'frito': 'freír', 'impreso': 'imprimir',
    'provisto': 'proveer',
}

# Common irregular gerunds
GERUNDS = {
    'diciendo': 'decir', 'durmiendo': 'dormir', 'pidiendo': 'pedir',
    'sintiendo': 'sentir', 'vistiendo': 'vestir', 'muriendo': 'morir',
    'viniendo': 'venir', 'yendo': 'ir', 'oyendo': 'oír',
    'leyendo': 'leer', 'cayendo': 'caer', 'creyendo': 'creer',
    'trayendo': 'traer', 'construyendo': 'construir',
}

# Known names (common personal names in the textbook)
KNOWN_NAMES = {
    'lorena', 'paco', 'ana', 'susana', 'tomás', 'tomas',
    'li', 'meilan', 'manolo', 'elena', 'juan', 'maría', 'maria',
    'josé', 'jose', 'carlos', 'luis', 'pedro', 'miguel', 'lucía', 'lucia',
    'carmen', 'rosa', 'david', 'pablo', 'javier', 'andrés', 'andres',
    'diegol', 'sara', 'laura', 'marta', 'sofía', 'sofia',
    'ramón', 'ramon', 'raúl', 'raul', 'pepe', 'pepa',
    'antonio', 'manuel', 'francisco', 'isabel', 'teresa',
    'fernando', 'alberto', 'cristina', 'patricia', 'alejandro',
    'daniel', 'sandra', 'beatriz', 'ricardo', 'enrique',
    'alicia', 'vicente', 'roberto', 'gloria', 'eduardo',
    'julio', 'silvia', 'oscar', 'óscar', 'alfredo', 'lola',
    'jaime', 'guillermo', 'rafael', 'gonzalo', 'emilio',
    'arturo', 'hugo', 'álvaro', 'alvaro',
    'catalina', 'felipe', 'andrea', 'diego', 'gabriel',
    'adrián', 'adrian', 'martín', 'martin', 'nuria',
    'blanca', 'fina', 'paqui', 'mercedes', 'concha',
    'rafa', 'chema', 'alba', 'inés', 'ines',
    'señor', 'señora', 'señorita', 'don', 'doña',
    'méxico', 'méjico',
    # cities/countries that might appear
    'madrid', 'barcelona', 'sevilla', 'valencia', 'parís', 'paris',
    'londres', 'roma', 'berlín', 'berlin', 'nueva york',
    'buenos aires', 'lima', 'bogotá', 'bogota', 'santiago',
    'españa', 'espa', 'francia', 'italia', 'alemania', 'inglaterra',
    'portugal', 'china', 'japón', 'japon', 'estados unidos',
    'argentina', 'mexico', 'méxico', 'cuba', 'chile', 'panamá', 'panama',
    'perú', 'peru', 'colombia', 'venezuela', 'ecuador', 'bolivia',
    'uruguay', 'paraguay', 'costa rica', 'nicaragua', 'honduras',
    'guatemala', 'el salvador', 'república dominicana',
    'puerto rico', 'filipinas', 'guinea ecuatorial',
    'brasil', 'canadá', 'canada', 'rusia', 'australia',
    'sudáfrica', 'egipto', 'marruecos', 'argelia',
    # Regions, rivers, mountains etc
    'andes', 'amazonas', 'mediterráneo', 'atlántico', 'pacífico',
    'caribe', 'pirineos', 'alpes',
}

# Words that are always considered "known" (common interjections, greetings)
ALWAYS_KNOWN = {
    'hola', 'adiós', 'gracias', 'vale', 'eh', 'ah', 'oh', 'ay',
    'bueno', 'pues', 'vaya', 'anda', 'mira', 'oye', 'oiga',
    'buenos', 'buenas', 'días', 'tardes', 'noches',
    'sí', 'no', 'qué va',
    'señor', 'señora', 'señorita', 'don', 'doña',
    'san', 'santo', 'santa',
    'mamá', 'papá', 'mami', 'papi',
}

def parse_lesson(filepath):
    """Parse a lesson file, return (lesson_id, lesson_name, vocab_words, sentences)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract lesson ID from filename
    basename = os.path.basename(filepath)
    lesson_id = basename.replace('.txt', '')

    # Try to find lesson name (from first non-empty line or filename)
    lesson_name = lesson_id

    # Parse vocabulary section
    vocab_words = set()
    in_vocab = False
    in_sentences = False
    sentences = []

    for line in content.split('\n'):
        line = line.strip()

        if line.startswith('# 生词'):
            in_vocab = True
            in_sentences = False
            continue
        elif line.startswith('# 例句'):
            in_vocab = False
            in_sentences = True
            continue
        elif line.startswith('#') and (line.startswith('# 语法') or line.startswith('# 注释') or
                                        line.startswith('# 课文') or line.startswith('# 对话')):
            in_vocab = False
            in_sentences = False
            continue

        if in_vocab and line:
            # Extract the Spanish word (first token before definition)
            # Format: "word\tdefinition" or "word  definition" or "word definition"
            # Split on tab, or on space followed by Chinese/parenthesis
            parts = re.split(r'\t|(?<=[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]) (?=[一-鿿（）（）])', line, maxsplit=1)
            # If still no split, try splitting on 2+ spaces
            if len(parts) == 1:
                parts = re.split(r'  +', line, maxsplit=1)
            word = parts[0].strip().lower()
            if word and not word.startswith('(') and not word.startswith('（'):
                vocab_words.add(word)
                # Also add individual words from multi-word phrases
                # e.g., "buenos días" -> also add "buenos" and "días" separately
                subwords = word.split()
                if len(subwords) > 1:
                    for sw in subwords:
                        vocab_words.add(sw)

        if in_sentences and line:
            # Format: "Spanish sentence.\tChinese translation."
            # Or: "Spanish sentence. Chinese translation."
            # Split by tab first
            if '\t' in line:
                spanish_part = line.split('\t')[0].strip()
            else:
                spanish_part = line

            # Strip any Chinese characters that might have leaked in
            # (when tab split fails because format uses spaces)
            spanish_part = re.sub(r'[一-鿿　-〿＀-￯]+', '', spanish_part)
            # Also strip Chinese punctuation
            spanish_part = re.sub(r'[。，！？：；（）【】「」『』]', '', spanish_part)
            spanish_part = spanish_part.strip()

            if spanish_part and not spanish_part.startswith('(') and not spanish_part.startswith('（'):
                sentences.append(spanish_part)
            elif spanish_part.startswith('（') or spanish_part.startswith('('):
                # Skip lines like "（本课无完整西班牙语句子）"
                pass

    return lesson_id, lesson_name, vocab_words, sentences


def tokenize_sentence(sentence):
    """Extract individual Spanish words from a sentence."""
    # Remove punctuation but keep letters with accents
    cleaned = re.sub(r'[¿¡!?,.:;()""«»—\[\]{}……]', ' ', sentence)
    words = cleaned.split()
    # Only keep words that are Spanish/Latin characters (with accents and ñ)
    # Filter out Chinese, numbers-only, and empty strings
    result = []
    for w in words:
        w = w.strip().lower()
        if not w:
            continue
        # Check if the word contains at least one Latin letter (a-z with accents)
        if re.search(r'[a-záéíóúüñ]', w):
            # Further clean: remove any non-Latin chars that might be mixed in
            w = re.sub(r'[^a-záéíóúüñ]', '', w)
            if w:
                result.append(w)
    return result


def normalize_word(word):
    """Try to normalize a word to its base form. Returns list of possible base forms."""
    results = set()
    results.add(word)

    # Check verb forms dictionary
    if word in VERB_FORMS:
        results.add(VERB_FORMS[word])

    # Check past participles
    if word in PAST_PARTICIPLES:
        results.add(PAST_PARTICIPLES[word])

    # Check gerunds
    if word in GERUNDS:
        results.add(GERUNDS[word])

    # Strip attached object pronouns from infinitives, gerunds, imperatives
    # e.g., conocerlos -> conocer, decírmelo -> decir, mirándote -> mirar
    pronoun_suffixes = ['melo', 'telo', 'selo', 'noslo', 'oslo',
                        'mela', 'tela', 'sela', 'nosla', 'osla',
                        'melos', 'telos', 'selos', 'noslos', 'oslos',
                        'melas', 'telas', 'selas', 'noslas', 'oslas',
                        'me', 'te', 'se', 'nos', 'os',
                        'lo', 'la', 'los', 'las', 'le', 'les']
    for suffix in sorted(pronoun_suffixes, key=len, reverse=True):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            stem = word[:-len(suffix)]
            results.add(stem)
            # If stem ends in -r, it's likely an infinitive
            # If stem ends in -ndo, it's a gerund (after accent removal)
            # Try adding -r for truncated infinitives
            if not stem.endswith('r') and not stem.endswith('a') and not stem.endswith('e'):
                if len(stem) >= 2:
                    results.add(stem + 'r')
                    results.add(stem + 'ar')
                    results.add(stem + 'er')
                    results.add(stem + 'ir')
            break  # Only strip the longest matching suffix

    # Plural -> singular patterns
    # Always try removing -s (for vowel-ending words: chica->chicas, estudiante->estudiantes)
    if word.endswith('s'):
        results.add(word[:-1])

    # Try removing -es (for consonant-ending words: pared->paredes, móvil->móviles)
    if word.endswith('es') and len(word) > 3:
        base = word[:-2]
        results.add(base)
        # Handle accented plurals: jóvenes -> joven
        results.add(base.replace('ó', 'o').replace('é', 'e').replace('í', 'i').replace('á', 'a').replace('ú', 'u'))
        # lápices -> lápiz
        if base.endswith('c'):
            results.add(base[:-1] + 'z')

    # Feminine -> masculine: -a -> -o
    if word.endswith('a'):
        results.add(word[:-1] + 'o')

    # Masculine -> feminine: -o -> -a
    if word.endswith('o'):
        results.add(word[:-1] + 'a')

    # Diminutives: -ito/-ita, -illo/-illa, -cito/-cita
    if word.endswith('ito'):
        results.add(word[:-3] + 'o')
    if word.endswith('ita'):
        results.add(word[:-3] + 'a')
        results.add(word[:-3] + 'o')
    if word.endswith('illo'):
        results.add(word[:-4] + 'o')
    if word.endswith('illa'):
        results.add(word[:-4] + 'a')
        results.add(word[:-4] + 'o')
    if word.endswith('cito'):
        results.add(word[:-4] + 'o')
        results.add(word[:-4] + 'z' + 'o')  # e.g., piececito -> piezo? No... let's keep simple
    if word.endswith('cita'):
        results.add(word[:-4] + 'a')

    # Adverb -mente: remove it
    if word.endswith('mente') and len(word) > 6:
        base = word[:-5]
        results.add(base)
        # también -> tan bien?? No, también is its own word
        # But for claramente -> clara, claro
        results.add(base + 'o')
        results.add(base + 'a')

    # Superlative -ísimo/-ísima
    if word.endswith('ísimo'):
        results.add(word[:-5] + 'o')
    if word.endswith('ísima'):
        results.add(word[:-5] + 'a')
        results.add(word[:-5] + 'o')

    # Verb conjugation pattern matching
    # -ar verbs: -o, -as, -a, -amos, -áis, -an
    for suffix_inf, suffix_pat in [('ar', ['o', 'as', 'a', 'amos', 'áis', 'an',
                                             'aba', 'abas', 'ábamos', 'abais', 'aban',
                                             'é', 'aste', 'ó', 'amos', 'asteis', 'aron',
                                             'aré', 'arás', 'ará', 'aremos', 'aréis', 'arán',
                                             'aría', 'arías', 'aríamos', 'aríais', 'arían'])]:
        for suf in suffix_pat:
            if word.endswith(suf) and len(word) > len(suf) + 2:
                stem = word[:-len(suf)]
                results.add(stem + suffix_inf)

    # -er verbs: -o, -es, -e, -emos, -éis, -en
    for suffix_inf, suffix_pat in [('er', ['o', 'es', 'e', 'emos', 'éis', 'en',
                                             'ía', 'ías', 'íamos', 'íais', 'ían',
                                             'í', 'iste', 'ió', 'imos', 'isteis', 'ieron',
                                             'eré', 'erás', 'erá', 'eremos', 'eréis', 'erán',
                                             'ería', 'erías', 'eríamos', 'eríais', 'erían'])]:
        for suf in suffix_pat:
            if word.endswith(suf) and len(word) > len(suf) + 2:
                stem = word[:-len(suf)]
                results.add(stem + suffix_inf)

    # -ir verbs: -o, -es, -e, -imos, -ís, -en
    for suffix_inf, suffix_pat in [('ir', ['o', 'es', 'e', 'imos', 'ís', 'en',
                                             'ía', 'ías', 'íamos', 'íais', 'ían',
                                             'í', 'iste', 'ió', 'imos', 'isteis', 'ieron',
                                             'iré', 'irás', 'irá', 'iremos', 'iréis', 'irán',
                                             'iría', 'irías', 'iríamos', 'iríais', 'irían'])]:
        for suf in suffix_pat:
            if word.endswith(suf) and len(word) > len(suf) + 2:
                stem = word[:-len(suf)]
                results.add(stem + suffix_inf)

    # Present subjunctive -ar: -e, -es, -e, -emos, -éis, -en
    for suf in ['e', 'es', 'e', 'emos', 'éis', 'en']:
        if word.endswith(suf) and len(word) > len(suf) + 2:
            stem = word[:-len(suf)]
            results.add(stem + 'ar')

    # Present subjunctive -er/-ir: -a, -as, -a, -amos, -áis, -an
    for suf in ['a', 'as', 'a', 'amos', 'áis', 'an']:
        if word.endswith(suf) and len(word) > len(suf) + 2:
            stem = word[:-len(suf)]
            results.add(stem + 'er')
            results.add(stem + 'ir')

    return results


def strip_accents(s):
    """Remove Spanish accents from a string."""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n',  # ñ is a different letter but sometimes confused
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U', 'Ñ': 'N',
    }
    result = s
    for accented, plain in replacements.items():
        result = result.replace(accented, plain)
    return result


def check_word_in_vocab(word, vocab_set, vocab_no_accent=None):
    """Check if a word or any of its normalized forms is in the vocabulary."""
    if word in ALWAYS_KNOWN:
        return True, None

    if word in KNOWN_NAMES:
        return True, None

    # Also check accent-stripped version against known names
    if strip_accents(word) in KNOWN_NAMES:
        return True, None

    # Direct match
    if word in vocab_set:
        return True, None

    # Accent-insensitive direct match
    if vocab_no_accent is not None and strip_accents(word) in vocab_no_accent:
        return True, None

    # Try normalized forms
    normalized = normalize_word(word)

    # Second pass: for each normalized form, try gender swap and common patterns
    expanded = set(normalized)
    for nf in normalized:
        # Gender swap: -a -> -o
        if nf.endswith('a'):
            expanded.add(nf[:-1] + 'o')
        # Gender swap: -o -> -a
        if nf.endswith('o'):
            expanded.add(nf[:-1] + 'a')
        # Consonant-stem feminine: profesora -> profesor (strip -a)
        if nf.endswith('a') and len(nf) > 3:
            expanded.add(nf[:-1])
        # Remove -s (plural)
        if nf.endswith('s') and len(nf) > 3:
            expanded.add(nf[:-1])
        # Remove -es (plural for consonant-ending words)
        if nf.endswith('es') and len(nf) > 4:
            expanded.add(nf[:-2])

    for nf in expanded:
        if nf in vocab_set:
            return True, None
        # Accent-insensitive check
        if vocab_no_accent is not None and strip_accents(nf) in vocab_no_accent:
            return True, None

    # For multi-word phrases in vocab, check if this word appears as part
    for vw in vocab_set:
        if ' ' in vw:
            if word in vw.split():
                return True, None
            # Also check accent-insensitive
            if strip_accents(word) in [strip_accents(w) for w in vw.split()]:
                return True, None

    return False, normalized


def audit_all():
    """Main audit function."""
    files = sorted(glob.glob(os.path.join(BASE_DIR, '*.txt')),
                   key=lambda x: os.path.basename(x))

    accumulated_vocab = set()
    accumulated_vocab_no_accent = set()
    results = []
    total_missing = 0
    lesson_count = 0

    for filepath in files:
        lesson_id, lesson_name, vocab_words, sentences = parse_lesson(filepath)

        # Add this lesson's vocab to accumulated
        accumulated_vocab.update(vocab_words)
        for vw in vocab_words:
            accumulated_vocab_no_accent.add(strip_accents(vw))

        missing_in_lesson = []

        for sentence in sentences:
            words = tokenize_sentence(sentence)
            for word in words:
                # Skip empty or pure punctuation
                if not word or len(word) <= 1:
                    continue

                # Skip function words
                if word in FUNCTION_WORDS:
                    continue

                # Check if word or its base form is known
                found, normalized_forms = check_word_in_vocab(
                    word, accumulated_vocab, accumulated_vocab_no_accent)

                if not found:
                    # Find the suggested base form
                    suggested_base = word
                    if normalized_forms and len(normalized_forms) > 1:
                        # Pick the most likely base form (shortest, non-identical)
                        bases = [f for f in normalized_forms if f != word]
                        if bases:
                            suggested_base = min(bases, key=len)

                    # Check if already reported for this lesson
                    entry = (word, suggested_base, sentence)
                    if not any(e[0] == word and e[2] == sentence for e in missing_in_lesson):
                        missing_in_lesson.append(entry)

        if missing_in_lesson:
            lesson_count += 1
            total_missing += len(missing_in_lesson)
            results.append((lesson_id, lesson_name, missing_in_lesson))

    # Print results
    print("=" * 80)
    print("VOCABULARY COVERAGE AUDIT - MISSING WORDS BY LESSON")
    print("=" * 80)

    for lesson_id, lesson_name, missing in results:
        print(f"\n## {lesson_id}")
        for word, base, sentence in sorted(missing, key=lambda x: x[0]):
            print(f"  - **{word}** (posible base: {base}) - aparece en: \"{sentence}\"")

    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {lesson_count} lessons have potential missing vocabulary words.")
    print(f"Total potential missing entries: {total_missing}")
    print(f"{'=' * 80}")

    # Lessons with issues summary
    print(f"\nLessons with issues:")
    for lesson_id, lesson_name, missing in results:
        unique_words = sorted(set(w for w, b, s in missing))
        print(f"  {lesson_id}: {len(unique_words)} unique words - {', '.join(unique_words)}")


if __name__ == '__main__':
    audit_all()
