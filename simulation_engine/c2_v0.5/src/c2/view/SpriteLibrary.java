package c2.view;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Loads the drone sprite (Kenney craft_speederA, CC0) and crops away its empty border. Optional. */
public class SpriteLibrary {
    private final BufferedImage drone;

    public SpriteLibrary(Path assetsFolder) {
        this.drone = loadCropped(assetsFolder.resolve("kenney/space/craft_speederA_SE.png"));
    }

    /** Null if the asset isn't found; the view then falls back to a drawn symbol. */
    public BufferedImage drone() { return drone; }

    private static BufferedImage loadCropped(Path file) {
        if (!Files.exists(file)) return null;
        try {
            BufferedImage full = ImageIO.read(file.toFile());
            int left = full.getWidth(), top = full.getHeight(), right = -1, bottom = -1;
            for (int y = 0; y < full.getHeight(); y++) {
                for (int x = 0; x < full.getWidth(); x++) {
                    if ((full.getRGB(x, y) >>> 24) > 10) {
                        left = Math.min(left, x); right = Math.max(right, x);
                        top = Math.min(top, y); bottom = Math.max(bottom, y);
                    }
                }
            }
            return right < 0 ? null : full.getSubimage(left, top, right - left + 1, bottom - top + 1);
        } catch (IOException problem) {
            System.err.println("Could not load " + file + ": " + problem.getMessage());
            return null;
        }
    }
}
