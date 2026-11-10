package c2.input;

/** Anything that accepts commands. Each sink ignores command types that aren't its business. */
public interface CommandSink {
    void submit(Command command);
}
