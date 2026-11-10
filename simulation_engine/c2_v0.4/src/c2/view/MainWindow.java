package c2.view;

import javax.swing.JFrame;
import java.awt.BorderLayout;
import java.awt.event.KeyListener;

/** The window: board in the center, SITREP on the right. */
public class MainWindow extends JFrame {
    public MainWindow(IsoBoardView board, SitrepPanel sitrep, KeyListener keys) {
        super("C2 Operations Picture — Operation Lost and Found — " + c2.app.Version.VERSION);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLayout(new BorderLayout());
        add(board, BorderLayout.CENTER);
        add(sitrep, BorderLayout.EAST);
        addKeyListener(keys);
        board.addKeyListener(keys);
        pack();
        setLocationRelativeTo(null);
    }
}
