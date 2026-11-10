package c2.model;

import java.util.Collection;

/** Probability the subject is in each square. Always sums to 1. */
public class BeliefGrid {
    private final int rows, cols;
    private double[][] chance;

    public BeliefGrid(int rows, int cols) {
        this.rows = rows;
        this.cols = cols;
        this.chance = new double[rows][cols];
    }

    public double at(int row, int col) { return chance[row][col]; }
    public int rows() { return rows; }
    public int cols() { return cols; }

    /** Starting guess: Gaussian around the last known location, weighted by terrain pull. */
    public void seedGaussian(GridPos center, double sigmaCells, TerrainGrid terrain) {
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double distanceSquared = Math.pow(row - center.row(), 2) + Math.pow(col - center.col(), 2);
                chance[row][col] = Math.exp(-distanceSquared / (2 * sigmaCells * sigmaCells))
                        * terrain.at(row, col).cover().pull;
            }
        }
        normalize();
    }

    /** A sweep that found nothing: each swept square drops by its chance of detection. */
    public void applyMiss(Collection<GridPos> swept, TerrainGrid terrain, double coverage) {
        for (GridPos pos : swept) {
            double detectionChance = coverage * terrain.at(pos).cover().sensorFactor;
            chance[pos.row()][pos.col()] *= (1 - detectionChance);
        }
        normalize();
    }

    /** A sighting: squares near it rise sharply. */
    public void applySighting(GridPos pos, double radiusCells) {
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double distanceSquared = Math.pow(row - pos.row(), 2) + Math.pow(col - pos.col(), 2);
                chance[row][col] *= 0.02 + Math.exp(-distanceSquared / (2 * radiusCells * radiusCells));
            }
        }
        normalize();
    }

    /**
     * Time passes: the subject may have walked. Each square keeps most of its probability and
     * shares the rest with its 4 neighbors, more toward easy, attractive ground, none across water or cliffs.
     */
    public void spread(TerrainGrid terrain, double movingFraction) {
        double[][] next = new double[rows][cols];
        int[][] steps = {{-1, 0}, {1, 0}, {0, -1}, {0, 1}};
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double here = chance[row][col];
                if (here == 0) continue;
                double[] weights = new double[4];
                double totalWeight = 0;
                for (int step = 0; step < 4; step++) {
                    int nextRow = row + steps[step][0], nextCol = col + steps[step][1];
                    if (nextRow < 0 || nextRow >= rows || nextCol < 0 || nextCol >= cols) continue;
                    TerrainCell neighbor = terrain.at(nextRow, nextCol);
                    if (neighbor.cover().blocksWalking() || neighbor.cliff()) continue;
                    weights[step] = neighbor.cover().pull / neighbor.cover().walkCost;
                    totalWeight += weights[step];
                }
                double moving = totalWeight > 0 ? here * movingFraction : 0;
                next[row][col] += here - moving;
                for (int step = 0; step < 4; step++) {
                    if (weights[step] > 0) {
                        next[row + steps[step][0]][col + steps[step][1]] += moving * weights[step] / totalWeight;
                    }
                }
            }
        }
        chance = next;
        normalize();
    }

    public double max() {
        double highest = 0;
        for (double[] row : chance) for (double value : row) highest = Math.max(highest, value);
        return highest;
    }

    /** Spread-out-ness. High = could be anywhere, low = narrowed down. */
    public double entropy() {
        double total = 0;
        for (double[] row : chance) for (double value : row) if (value > 0) total -= value * Math.log(value);
        return total;
    }

    private void normalize() {
        double sum = 0;
        for (double[] row : chance) for (double value : row) sum += value;
        if (sum <= 0) return;
        for (double[] row : chance) for (int col = 0; col < row.length; col++) row[col] /= sum;
    }
}
