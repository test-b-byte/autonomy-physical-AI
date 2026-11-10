package c2.observe;

/** What changed in the picture, so views can redraw only what they need. */
public record PictureEvent(PictureEventType type, String detail) { }
