package c2.ingest;

import c2.model.DroneReport;
import c2.model.GridPos;
import c2.model.MedicalReport;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Adapter: drone report JSON files -> DroneReport. Watches an inbox folder; a returning drone's
 * file is read, put on the queue, and moved to inbox/processed.
 *
 * Format:
 * { "sortie_id": "S1", "returned_at": "2026-11-08T14:12:00Z",
 *   "swept_cells": [[row,col],...], "sighting": [row,col] | null, "hazards_seen": [[row,col],...],
 *   "hostiles_seen": [[row,col],...],
 *   "medical": {"app_version": "v0.5", "values": [0,1,...], "needs_attention": ["..."]} | null }
 */
public class DroneReportFolderAdapter implements FeedAdapter {
    private final Path inbox;
    private final Path processed;
    private ScheduledExecutorService watcher;

    public DroneReportFolderAdapter(Path inbox) {
        this.inbox = inbox;
        this.processed = inbox.resolve("processed");
    }

    @Override public String name() { return "drone reports: " + inbox; }

    @Override
    public void start(InboundQueue queue) {
        ensureFolders();
        watcher = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "report-inbox");
            thread.setDaemon(true);
            return thread;
        });
        watcher.scheduleWithFixedDelay(() -> scanOnce(queue), 0, 500, TimeUnit.MILLISECONDS);
    }

    @Override public void stop() { if (watcher != null) watcher.shutdownNow(); }

    /** Public so headless runs can scan without the timer. */
    public void scanOnce(InboundQueue queue) {
        ensureFolders();
        try (DirectoryStream<Path> files = Files.newDirectoryStream(inbox, "*.json")) {
            for (Path file : files) {
                try {
                    queue.put(parse(Files.readString(file)));
                } catch (RuntimeException badFile) {
                    System.err.println("Skipping unreadable report " + file + ": " + badFile.getMessage());
                }
                Files.move(file, processed.resolve(file.getFileName()), StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException problem) {
            System.err.println("Inbox scan failed: " + problem.getMessage());
        }
    }

    private void ensureFolders() {
        try {
            Files.createDirectories(processed);
        } catch (IOException problem) {
            throw new IllegalStateException("cannot create " + processed, problem);
        }
    }

    @SuppressWarnings("unchecked")
    static DroneReport parse(String json) {
        Map<String, Object> root = (Map<String, Object>) MiniJson.parse(json);
        Map<String, Object> medicalJson = (Map<String, Object>) root.get("medical");
        MedicalReport medical = null;
        if (medicalJson != null) {
            List<Integer> values = new ArrayList<>();
            for (Object value : (List<Object>) medicalJson.get("values")) {
                values.add(value == null ? null : ((Double) value).intValue());
            }
            List<String> attention = new ArrayList<>();
            Object attentionJson = medicalJson.get("needs_attention");
            if (attentionJson != null) for (Object item : (List<Object>) attentionJson) attention.add((String) item);
            medical = new MedicalReport(values, attention, String.valueOf(medicalJson.get("app_version")));
        }
        return new DroneReport(
                String.valueOf(root.get("sortie_id")),
                Instant.parse((String) root.get("returned_at")),
                cells(root.get("swept_cells")),
                root.get("sighting") == null ? null : cell((List<Object>) root.get("sighting")),
                medical,
                cells(root.get("hazards_seen")),
                cells(root.get("hostiles_seen")));
    }

    @SuppressWarnings("unchecked")
    private static List<GridPos> cells(Object json) {
        List<GridPos> cells = new ArrayList<>();
        if (json != null) for (Object pair : (List<Object>) json) cells.add(cell((List<Object>) pair));
        return cells;
    }

    private static GridPos cell(List<Object> pair) {
        return new GridPos(((Double) pair.get(0)).intValue(), ((Double) pair.get(1)).intValue());
    }
}
