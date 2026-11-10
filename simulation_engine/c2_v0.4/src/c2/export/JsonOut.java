package c2.export;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class JsonOut {
    private JsonOut() { }

    /** Write to a temp file, then swap it in, so readers never see a half-written file. */
    static void write(Path target, String json) {
        try {
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            Files.writeString(temp, json);
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException problem) {
            System.err.println("Write failed " + target + ": " + problem.getMessage());
        }
    }
}
