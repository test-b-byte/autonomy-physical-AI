package c2.observe;

import javax.swing.SwingUtilities;

/**
 * Wraps a Swing view. The picture changes on the clock thread; Swing may only be touched
 * on its own thread, so every notification is handed over with invokeLater.
 */
public class SwingObserverBridge implements PictureObserver {
    private final PictureObserver view;

    public SwingObserverBridge(PictureObserver view) { this.view = view; }

    @Override
    public void onPictureChanged(PictureEvent event) {
        if (SwingUtilities.isEventDispatchThread()) view.onPictureChanged(event);
        else SwingUtilities.invokeLater(() -> view.onPictureChanged(event));
    }
}
