package c2.app;

import c2.export.MapStateWriter;
import c2.export.MissionOrderWriter;
import c2.export.PathExporter;
import c2.ingest.DroneReportFolderAdapter;
import c2.ingest.InboundQueue;
import c2.ingest.SimulatedDroneFeed;
import c2.input.CommandSink;
import c2.input.SwingInputAdapter;
import c2.mission.MissionController;
import c2.model.OperationsPicture;
import c2.observe.SwingObserverBridge;
import c2.search.LocalSearchEngine;
import c2.search.SearchEngine;
import c2.time.SimClock;
import c2.view.Camera;
import c2.view.IsoBoardView;
import c2.view.MainWindow;
import c2.view.SitrepPanel;
import c2.view.SpriteLibrary;
import c2.view.TerrainImageCache;

import javax.swing.SwingUtilities;
import java.nio.file.Path;
import java.util.List;

/** Wires everything together. Model and controller know nothing about Swing; views only observe. */
public class C2App {
    public final OperationsPicture picture;
    public final SimClock clock;
    public final MissionController controller;
    public final Camera camera;
    public final TerrainImageCache terrainCache;
    public final SpriteLibrary sprites;
    public final DroneReportFolderAdapter reportAdapter;
    public final InboundQueue queue = new InboundQueue();

    public C2App(Path inbox, Path outFolder, Path assets, Path roomFile, boolean simulateDrone) {
        c2.model.RoomFeatures room = Scenario.loadRoom(roomFile);
        System.out.println(room == null ? "No room map (" + roomFile + "): generated terrain only"
                : "Room map loaded: " + room.mountains().size() + " hill squares, casualty at " + room.casualty());
        picture = Scenario.build(room);
        clock = new SimClock(Scenario.START, 250);
        SearchEngine engine = new LocalSearchEngine();
        SimulatedDroneFeed simulated = simulateDrone
                ? new SimulatedDroneFeed(inbox, Scenario.FRAME, picture.terrain(), Scenario.trueSubject(room), 7) : null;
        controller = new MissionController(picture, engine, queue, simulated,
                new MissionOrderWriter(outFolder, Scenario.FRAME), new PathExporter(outFolder, Scenario.FRAME),
                new MapStateWriter(outFolder), Scenario.SUBJECT, Scenario.DRONES, Scenario.TOC, Scenario.STAGING,
                Scenario.TEAM, Scenario.LAST_KNOWN, "Locate the lost hiker, assess casualty, guide rescue.");
        reportAdapter = new DroneReportFolderAdapter(inbox);
        camera = new Camera(Scenario.FRAME.rows(), Scenario.FRAME.cols(),
                86, 72, 1);
        terrainCache = new TerrainImageCache(picture.terrain(), Scenario.FRAME.rows(), Scenario.FRAME.cols());
        sprites = new SpriteLibrary(assets);
        clock.addListener(controller);
    }

    public void startHeadless() {
        reportAdapter.start(queue);
        controller.begin();
    }

    public void startWithWindow() {
        SwingUtilities.invokeLater(() -> {
            terrainCache.image(camera.tileWidth());                  // pre-draw terrain before showing
            IsoBoardView board = new IsoBoardView(picture, terrainCache, camera, sprites);
            SitrepPanel sitrep = new SitrepPanel(picture, clock);
            picture.addObserver(new SwingObserverBridge(board));
            picture.addObserver(new SwingObserverBridge(sitrep));
            camera.setOnChange(board::repaint);
            List<CommandSink> sinks = List.of(clock, controller, camera, board);
            MainWindow window = new MainWindow(board, sitrep, new SwingInputAdapter(sinks));
            window.setVisible(true);
            board.requestFocusInWindow();
            startHeadless();
            clock.start();
        });
    }
}
