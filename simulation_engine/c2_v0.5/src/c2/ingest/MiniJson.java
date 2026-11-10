package c2.ingest;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Tiny JSON reader (objects -> Map, arrays -> List, numbers -> Double). Avoids external libraries. */
public final class MiniJson {
    private final String text;
    private int index;

    private MiniJson(String text) { this.text = text; }

    public static Object parse(String text) {
        MiniJson parser = new MiniJson(text);
        Object value = parser.readValue();
        parser.skipSpace();
        if (parser.index != text.length()) throw new IllegalArgumentException("extra text at " + parser.index);
        return value;
    }

    private Object readValue() {
        skipSpace();
        char next = text.charAt(index);
        if (next == '{') return readObject();
        if (next == '[') return readArray();
        if (next == '"') return readString();
        if (text.startsWith("true", index)) { index += 4; return Boolean.TRUE; }
        if (text.startsWith("false", index)) { index += 5; return Boolean.FALSE; }
        if (text.startsWith("null", index)) { index += 4; return null; }
        return readNumber();
    }

    private Map<String, Object> readObject() {
        Map<String, Object> map = new LinkedHashMap<>();
        index++;
        skipSpace();
        if (text.charAt(index) == '}') { index++; return map; }
        boolean more = true;
        while (more) {
            skipSpace();
            String key = readString();
            skipSpace();
            expect(':');
            map.put(key, readValue());
            skipSpace();
            more = text.charAt(index) == ',';
            index++;
        }
        return map;
    }

    private List<Object> readArray() {
        List<Object> list = new ArrayList<>();
        index++;
        skipSpace();
        if (text.charAt(index) == ']') { index++; return list; }
        boolean more = true;
        while (more) {
            list.add(readValue());
            skipSpace();
            more = text.charAt(index) == ',';
            index++;
        }
        return list;
    }

    private String readString() {
        expect('"');
        StringBuilder builder = new StringBuilder();
        while (text.charAt(index) != '"') {
            char next = text.charAt(index++);
            if (next == '\\') {
                char escaped = text.charAt(index++);
                switch (escaped) {
                    case 'n' -> builder.append('\n');
                    case 't' -> builder.append('\t');
                    case 'u' -> { builder.append((char) Integer.parseInt(text.substring(index, index + 4), 16)); index += 4; }
                    default -> builder.append(escaped);
                }
            } else {
                builder.append(next);
            }
        }
        index++;
        return builder.toString();
    }

    private Double readNumber() {
        int start = index;
        while (index < text.length() && "+-0123456789.eE".indexOf(text.charAt(index)) >= 0) index++;
        return Double.parseDouble(text.substring(start, index));
    }

    private void skipSpace() {
        while (index < text.length() && Character.isWhitespace(text.charAt(index))) index++;
    }

    private void expect(char wanted) {
        if (text.charAt(index) != wanted) throw new IllegalArgumentException("expected " + wanted + " at " + index);
        index++;
    }
}
