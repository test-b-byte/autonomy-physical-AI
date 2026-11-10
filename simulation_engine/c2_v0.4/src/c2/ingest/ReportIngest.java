package c2.ingest;

import c2.model.Alert;
import c2.model.AlertLevel;
import c2.model.DroneReport;
import c2.model.Knowledge;
import c2.model.MapObject;
import c2.model.ObjectKind;
import c2.model.OperationsPicture;
import c2.model.Source;
import c2.observe.PictureEventType;
import c2.search.SearchEngine;

/** Applies a returned drone's report to the picture: evidence to the engine, HOLO -> SOLID, alerts. */
public final class ReportIngest {
    private static final double HOSTILE_MATCH_CELLS = 8;

    private ReportIngest() { }

    public static void apply(OperationsPicture picture, SearchEngine engine, DroneReport report, String subjectId) {
        engine.applyReport(picture, report);

        MapObject subject = picture.object(subjectId);
        if (report.sighting() != null && subject != null) {
            subject.confirm(report.sighting(), report.returnedAt(), Source.REPORT);
            picture.countContact();
            picture.changed(PictureEventType.OBJECT_CONFIRMED, subjectId);
            picture.raise(new Alert(report.returnedAt(), AlertLevel.CONTACT,
                    "CONTACT " + report.sortieId() + " at " + report.sighting().row() + "," + report.sighting().col()));
        } else {
            picture.raise(new Alert(report.returnedAt(), AlertLevel.INFO,
                    report.sortieId() + " back: no contact, " + report.sweptCells().size() + " squares swept"));
        }

        if (report.medical() != null) {
            if (report.medical().isUrgent()) {
                picture.raise(new Alert(report.returnedAt(), AlertLevel.URGENT,
                        "URGENT CASUALTY: " + String.join(", ", report.medical().needsAttention())));
            } else if (report.medical().canEscort()) {
                picture.raise(new Alert(report.returnedAt(), AlertLevel.INFO, "Casualty can walk: escort possible"));
            }
        }

        for (var seen : report.hostilesSeen()) {                      // match each sighting to the nearest predicted hostile
            MapObject nearest = null;
            double nearestDistance = HOSTILE_MATCH_CELLS;
            for (MapObject object : picture.objects()) {
                if (object.kind() != ObjectKind.HOSTILE) continue;
                double distance = object.pos().distanceTo(seen);
                if (distance <= nearestDistance) { nearest = object; nearestDistance = distance; }
            }
            if (nearest != null) {
                nearest.confirm(seen, report.returnedAt(), Source.REPORT);
                picture.changed(PictureEventType.OBJECT_CONFIRMED, nearest.id());
                picture.raise(new Alert(report.returnedAt(), AlertLevel.CONTACT, "Hostile confirmed: " + nearest.label()));
            }
        }

        int hazardNumber = 0;
        for (var hazardPos : report.hazardsSeen()) {
            String id = report.sortieId() + "-hazard-" + hazardNumber++;
            picture.add(new MapObject(id, ObjectKind.HAZARD, "HAZARD", hazardPos,
                    Knowledge.SOLID, Source.REPORT, report.returnedAt(), 1));
            picture.changed(PictureEventType.OBJECT_CONFIRMED, id);
        }
    }
}
