from collections import OrderedDict
from CellSim import *
import random
import Params


class BreakAll(Exception):
    pass

class PlantCell(WorldObject):
    WORLD = None
    PLANT = None
    ENERGY_PER_CELL = None

    def __init__(self, row, col):
        WorldObject.__init__(self, PlantCell.WORLD, row, col)

    def feed(self):
        PlantCell.PLANT.freePlantCell(self)
        return PlantCell.ENERGY_PER_CELL


class Plant(Model):
    AVAILABLE_ENERGY = 0

    def __init__(self, aWorld, maxPlantSize, energyPerCell, randGrowthFactor):
        Model.__init__(self)

        PlantCell.WORLD = aWorld
        PlantCell.PLANT = self
        PlantCell.ENERGY_PER_CELL = energyPerCell

        self._world = aWorld
        self._maxSize = maxPlantSize
        self._plantCells = OrderedDict()
        self._randGrowthFactor = randGrowthFactor
        self._availableGrowthEnergy = 0

    # Specialization of Subscriber
    def subscriptionTopics(self):
        return [ ]

    def handleMessage(self, aMsg):
        if aMsg.topic() == 'Energy Freed':
            self._availableGrowthEnergy += aMsg['units']
        elif aMsg.topic() == 'Plant Cell Eaten':
            plantCell = aMsg['cell']
            eater     = aMsg['sender']
            sendMessage('Gain Energy', eater, units=10)
            self.freePlantCell(plantCell)

    # Specialization of Model
    def tick(self):
        numPlantCellsToTryToGrow = min(self._maxSize - len(self._plantCells),
                                       Plant.AVAILABLE_ENERGY
                                          // Params.ENERGY_PER_PLANT_CELL)

        if numPlantCellsToTryToGrow < 20:
            return 0

        numPlantCellsGrown = self.grow(numPlantCellsToTryToGrow)

        Plant.AVAILABLE_ENERGY -= (numPlantCellsGrown
                                   * Params.ENERGY_PER_PLANT_CELL)

    # Extension
    def size(self):
        return len(self._plantCells)

    def startPlant(self, row, col):
        c = PlantCell(row, col)
        self._plantCells[c.ident()] = c
        self.tick()   # <- enter a growth cycle to prime the Plant

    def grow(self):
        raise NotImplementedError()

    def freePlantCell(self, aCell):
        del self._plantCells[aCell._ident]
        PlantCell.WORLD.remove(aCell._r, aCell._c, aCell)


class GeometricPlant(Plant):
    def __init__(self, aWorld, maxPlantSize, energyPerCell, randGrowthFactor):
        Plant.__init__(self, aWorld, maxPlantSize,
                       energyPerCell, randGrowthFactor)

    def grow(self, numPlantCellsToTryToGrow):
        numPlantCellsGrown = 0

        plantCellIds = list(self._plantCells.keys())
        newPlantCells = []
        for plantCellIdent in plantCellIds:
            plantRowCol = self._plantCells[plantCellIdent].position()
            for row,col in self._world.emptyCNeighbors(*plantRowCol):
                if numPlantCellsGrown >= numPlantCellsToTryToGrow:
                    return numPlantCellsGrown

                newCell = PlantCell(row, col)
                newPlantCells.append(newCell)
                numPlantCellsGrown += 1

        for newCell in newPlantCells:
            self._plantCells[newCell.ident()] = newCell

        return numPlantCellsGrown

class SinuousPlant(Plant):
    def __init__(self, aWorld, maxPlantSize, energyPerCell, randGrowthFactor):
        Plant.__init__( self, aWorld, maxPlantSize,
                        energyPerCell, randGrowthFactor)

    def grow(self, numPlantCellsToTryToGrow):
        numPlantCellsGrown = 0
        while numPlantCellsGrown < numPlantCellsToTryToGrow:
            revPlantCells = reversed(self._plantCells)
            newPlantCells = []
            try:
                for plantCellIdent in revPlantCells:
                    plantCell = self._plantCells[plantCellIdent]
                    plantRowCol = self._plantCells[plantCellIdent].position()

                    for row,col in self._world.emptyCNeighbors(*plantRowCol):
                        if numPlantCellsGrown >= numPlantCellsToTryToGrow:
                            raise BreakAll()

                        if random.random() < self._randGrowthFactor:
                            newCell = PlantCell(row, col)
                            newPlantCells.append(newCell)
                            numPlantCellsGrown += 1
                            break

            except BreakAll:
                pass

            for newCell in newPlantCells:
                self._plantCells[newCell.ident()] = newCell

        return numPlantCellsGrown


class SimpleCell(Cell):
    def __init__(self, aWorld, genes, generation=0,
                 ident=None, energy=0, row=None, col=None):
        Cell.__init__(self, aWorld, generation, ident, energy, row, col)
        self._currentState = 0
        self._genes = genes

    def tick(self):
        if self._energyStore <= 0:
            self._behavior_die()
        else:
            self._energyStore -= Params.ENERGY_PER_MOVE
            Plant.AVAILABLE_ENERGY += Params.ENERGY_PER_MOVE

            try:
                # Try to eat
                neighbors = self._world.cNeighborsOfType(self._r, self._c,
                                                         PlantCell)
                    # list neighbors who are plants

                plantCellInst = choice(neighbors)
                    # pick a neighbor at random <- throws if len(neighbors) == 0

                self._energyStore += plantCellInst.feed()
                    # eat the neighboring plant cell
            except:
                try:
                    if ((self._energyStore >= Params.WELL_FED_LEVEL)
                        and (self._age > Params.MATURITY)
                        and (Cell.POPULATION < Params.MAX_CELL_POPULATION)):
                        # If all conditions are met, perform cell division
                        self._behavior_clone()
                            # <- throws if no place to put a daughter
                    else:
                        nextDir = self._genes[self._currentState]
                        if nextDir != '_':
                            self._behavior_move(nextDir)
                        self._currentState += 1
                        self._currentState %= Params.GENOME_LENGTH
                except:
                    pass

            self._age += 1

    def _behavior_clone(self):
        # Determine where to place the daughter cell
        try:
            neighbors = self._world.emptyNeighbors(self._r, self._c)
            daughterRow,daughterCol = choice(neighbors)  # <- throws if len(neighbors) == 0
        except:
            return False

        # Create the daughter's genes
        daughterGenes = self._genes[:] # <- copy the mother's genes
        geneToMutate = randint(0,Params.GENOME_LENGTH-1)
        daughterGenes[geneToMutate] = choice(Params.GENES) # <- mutate

        # Perform the clone
        daughter = SimpleCell(self._world, daughterGenes,
                              self._generation + 1,
                              energy=self._energyStore // 2,
                              row=daughterRow, col=daughterCol)

        # Turn the mother into a daughter
        self._energyStore -= daughter._energyStore
        self._age    = 0

        # set her aloft
        self._sim.add(daughter)

        return True
