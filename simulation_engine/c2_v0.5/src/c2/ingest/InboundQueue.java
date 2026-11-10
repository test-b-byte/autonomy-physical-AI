package c2.ingest;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Thread-safe holding area. Adapters add whenever data arrives (any thread);
 * the controller drains it once per tick, so the model only changes at one predictable moment.
 */
public class InboundQueue {
    private final ConcurrentLinkedQueue<Object> items = new ConcurrentLinkedQueue<>();

    public void put(Object item) { items.add(item); }

    public List<Object> drain() {
        List<Object> drained = new ArrayList<>();
        Object item;
        while ((item = items.poll()) != null) drained.add(item);
        return drained;
    }
}
