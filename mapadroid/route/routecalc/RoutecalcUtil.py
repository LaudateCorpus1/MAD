import datetime
from typing import List, Tuple, Optional

import numpy as np
from loguru import logger

from mapadroid.db.helper import SettingsRoutecalcHelper
from mapadroid.db.model import SettingsRoutecalc
from mapadroid.route.routecalc.ClusteringHelper import ClusteringHelper
from mapadroid.utils.collections import Location
from sqlalchemy.ext.asyncio import AsyncSession


class RoutecalcUtil:
    @staticmethod
    async def get_json_route(session: AsyncSession, routecalc_id: int, coords: List[Location], max_radius,
                             max_coords_within_radius,
                             in_memory, num_processes, algorithm, use_s2, s2_level, route_name,
                             delete_old_route: bool = False):
        routecalc_entry: Optional[SettingsRoutecalc] = None
        if not routecalc_entry:
            # TODO: Can this even be the case? Handle correctly
            routecalc_entry = SettingsRoutecalc()
            routecalc_entry.routecalc_id = routecalc_id
        await session.merge(routecalc_entry)
        await session.refresh(routecalc_entry)

        routecalc_entry.recalc_status = 1
        session.add(routecalc_entry)
        # Commit to make the recalc_status visible to others
        await session.commit()
        await session.refresh(routecalc_entry)
        # TODO: Ensure the object is still valid later on
        if not in_memory:
            routecalc_entry: SettingsRoutecalc = await SettingsRoutecalcHelper.get(session, routecalc_id)
            if delete_old_route:
                logger.debug("Deleting routefile...")
                routecalc_entry.routefile = []
                session.add(routecalc_entry)
                await session.commit()
                await session.refresh(routecalc_entry)
            else:
                saved_route = RoutecalcUtil._read_saved_json_route(routecalc_entry)
                if saved_route:
                    logger.debug('Using routefile from DB')
                    return saved_route

        export_data = []
        if use_s2:
            logger.debug("Using S2 method for calculation with S2 level: {}", s2_level)

        # TODO: Move to method running calculation in a thread/executor...
        less_coords = coords
        if len(coords) > 0 and max_radius and max_coords_within_radius:
            logger.info("Calculating route for {}", route_name)
            new_coords = RoutecalcUtil.get_less_coords(coords, max_radius, max_coords_within_radius, use_s2, s2_level)
            less_coords = np.zeros(shape=(len(new_coords), 2))
            for i in range(len(less_coords)):
                less_coords[i][0] = new_coords[i][0]
                less_coords[i][1] = new_coords[i][1]
            logger.debug("Coords summed up: {}, that's just {} coords", less_coords, len(less_coords))
        logger.debug("Got {} coordinates", len(less_coords))
        if len(less_coords) < 3:
            logger.debug("less than 3 coordinates... not gonna take a shortest route on that")
            export_data = []
            for i in range(len(less_coords)):
                export_data.append({'lat': less_coords[i][0].item(),
                                    'lng': less_coords[i][1].item()})
        else:
            logger.info("Calculating a short route through all those coords. Might take a while")
            from timeit import default_timer as timer
            start = timer()
            from mapadroid.route.routecalc.calculate_route_all import \
                route_calc_all
            sol_best = route_calc_all(less_coords, route_name, num_processes, algorithm)

            end = timer()

            calc_dur = (end - start) / 60
            time_unit = 'minutes'
            if calc_dur < 1:
                calc_dur = int(calc_dur * 60)
                time_unit = 'seconds'

            logger.info("Calculated route for {} in {} {}", route_name, calc_dur, time_unit)

            for i in range(len(sol_best)):
                export_data.append({'lat': less_coords[int(sol_best[i])][0].item(),
                                    'lng': less_coords[int(sol_best[i])][1].item()})
        if not in_memory:
            calc_coords = []
            for coord in export_data:
                calc_coord = '%s,%s' % (coord['lat'], coord['lng'])
                calc_coords.append(calc_coord)
            # Only save if we aren't calculating in memory
            routecalc_entry.routefile = calc_coords
            routecalc_entry.last_updated = datetime.datetime.utcnow()
        routecalc_entry.recalc_status = 0
        session.add(routecalc_entry)
        await session.commit()
        return export_data

    @staticmethod
    def get_less_coords(np_coords: List[Location], max_radius: int, max_coords_within_radius: int,
                        use_s2: bool = False, s2_level: int = 15):
        """
        Clusters the coords inserted according to the parameters provided
        Args:
            np_coords:
            max_radius:
            max_coords_within_radius:
            use_s2:
            s2_level:

        Returns:

        """
        coordinates: List[Tuple[int, Location]] = []
        for coord in np_coords:
            coordinates.append(
                (0, coord)
            )

        clustering_helper = ClusteringHelper(max_radius=max_radius, max_count_per_circle=max_coords_within_radius,
                                             max_timedelta_seconds=0, use_s2=use_s2, s2_level=s2_level)
        clustered_events = clustering_helper.get_clustered(coordinates)
        coords_cleaned_up: List[Location] = []
        for event in clustered_events:
            coords_cleaned_up.append(event[1])
        return coords_cleaned_up

    @staticmethod
    def _read_saved_json_route(routecalc_entry: SettingsRoutecalc):
        result = []
        if routecalc_entry.routefile is not None:
            for line in routecalc_entry.routefile:
                if not line.strip():
                    continue
                line_split = line.split(',')
                result.append({'lat': float(line_split[0].strip()), 'lng': float(line_split[1].strip())})
        return result