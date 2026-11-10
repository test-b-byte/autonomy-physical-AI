package c2.ingest;

/** Adapter target: reads some outside source and puts model objects on the queue. */
public interface FeedAdapter {
    String name();
    void start(InboundQueue queue);
    void stop();
}
