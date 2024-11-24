








def Receive_(self, peer_socket, peer_obj: Neighbour_Peer):
        print('start receiving from peer with ID:', peer_obj.ID,'\n')
        time_out_thread = Thread(target=Time_out, args=(peer_obj,)).start()
        while peer_obj.Check_alive():
            readable, _, _ = select.select([peer_socket], [], [], 0.1)  # Check if the socket is readable
            if readable:
                try:
                    message = self.receive_all(peer_socket)
                    #check if the connection is still alive
                    if message is None:
                        with peer_obj.live_lock:
                            peer_obj.is_alive = False
                        break
                    peer_obj.update_time() # Update the last message time regardless of the message type
                    # Process the message
                    message_type, payload = messParser.parse_message(message)
                    if message_type == 'keep-alive':
                        print("REC: Received keep-alive message")
                    elif message_type == 'choke':
                        print("REC: Received choke message")
                        peer_obj.update_receive_status(State.peer_choking)
                    elif message_type == 'unchoke':
                        print("REC: Received unchoke message")
                        peer_obj.update_receive_status(State.peer_interested)
                    elif message_type == 'interested':
                        print("REC: Received interested message")
                        if True: #temporarily set to true
                            unchoke_message = messParser.construct_unchoke()
                            peer_obj.control_queue.put((unchoke_message, 'unchoke'))
                            peer_obj.update_send_status(State.am_interested)
                    elif message_type == 'not interested':
                        print("REC: Received not interested message")
                        peer_obj.update_send_status(State.am_choking)
                        choke_message = messParser.construct_choke()
                        peer_obj.control_queue.put((choke_message, 'choke'))
                    elif message_type == 'have':
                        if self.left == 0: continue
                        print(f"REC: Received have message for piece index {payload}")
                        # with self.general_update_lock:
                        #     if payload in self.chunks_left:
                        #         peer_obj.available_chunks.append(payload)
                        try:
                            filepath = payload.get('filepath')
                            piece_index = payload.get('piece_index')
                           # print(f"REC: Received have message for file {filepath} with piece index {piece_index} from peer with ID: {peer_obj.ID}")
                            if filepath and piece_index is not None and payload in self.chunks_left:
                                peer_obj.add_chunk(payload)
                        except Exception as e:
                            print(f"ERROR: Failed to process have message: {e}")

                    elif message_type == 'request':
                        #print(f"REC: Received request message for piece index {payload}")
                        # with peer_obj.queue_lock:
                        #     if payload not in peer_obj.request_queue and len(peer_obj.request_queue) < self.max_councurrent_request:
                        #         peer_obj.request_queue.append(payload)
                        if not isinstance(payload, dict) or 'filepath' not in payload or 'piece_index' not in payload:
                            print("ERROR: Invalid payload format received.")
                            # Ignore invalid payloads
                        else:
                            #print(f"REC: Received request message for file {payload.get('filepath')} with piece index {payload.get('piece_index')}")
                            filepath = payload.get('filepath')
                            piece_index = payload.get('piece_index')

                            with self.piece_thread_lock:
                                piece_thread = self.piece_thread

                            if piece_thread < 10:
                                put_thread = Thread(target=self.Putting_pieces_thread, args=(payload, filepath, piece_index, peer_obj, True)).start()
                                with self.piece_thread_lock:
                                    self.piece_thread += 1
                            else:
                                self.Putting_pieces_thread(payload, filepath, piece_index, peer_obj, False)

                                # print(f"INFO - Peer {peer_obj.ID}: Added request to queue. Current queue size: {len(peer_obj.request_queue)}")
                            #else:
                            #    print(f"INFO - Peer {peer_obj.ID}: Request ignored. Either already in queue or queue is full. Current queue size: {len(peer_obj.request_queue)}")


                    elif message_type == 'piece':
                        
                        filepath = payload['filepath']
                        piece_index = payload['piece_index']
                        chunk_data = payload['chunk_data']
                        #print("REC: Received message for piece index", piece_index, "from peer with ID:", peer_obj.ID)
                        if chunk_data is None or chunk_data == b'':
                            continue

                        # Get payload info
                        chunk_metadata = {key: payload[key] for key in ['filepath', 'piece_index']}
                        
                        # might use this later
                        # for neighbour_peer in self.peer_list:
                        #     if payload in neighbour_peer.available_chunks:
                        #         neighbour_peer.available_chunks.remove(payload)
                        have = False
                        with self.general_update_lock:
                            if chunk_metadata in self.chunks_left:
                                have = True
                                self.save_chunk_to_local_storage(filepath, piece_index, chunk_data)
                                
                                self.downloaded += 1 #here we download the whole piece
                                self.chunks_downloaded.append(chunk_metadata)
                                self.left -= 1
                                self.chunks_left.remove(chunk_metadata)

                        if have:
                            if peer_obj.ID not in self.count:  #doesnt need a lock since it is only accessed by this thread
                                self.count[peer_obj.ID] = 1
                            else:
                                self.count[peer_obj.ID] += 1

                            have_message = messParser.construct_have(filepath, piece_index)
                            for peer in self.peer_list:
                                if peer.sock is not None and peer_obj.ID != peer.ID:
                                    peer.control_queue.put((have_message, 'have'))  # Send have message to all peers except the sender

                            for neighbour_peer in self.peer_list:
                                with neighbour_peer.available_lock:
                                    if chunk_metadata in neighbour_peer.available_chunks:
                                        neighbour_peer.available_chunks.remove(chunk_metadata) 

                            if self.left == 0:
                                print("REC: Download complete")
                                #Make a HTTP GET request to the tracker with the event 'completed'

                                params = {
                                "info_hash": self.info_hash,
                                "ip": "127.0.0.1",  # Your IP address
                                "peer_id": self.peer_id,  #Assign a unique peer ID
                                "port": self.port,  # Port your client listens on for incoming peer connections
                                "downloaded": self.downloaded,
                                # "downloaded": self.downloaded,
                                "left": self.left,  # Placeholder for the amount left to download
                                # "compact": 1, #reserved for future use
                                "event": "completed"
                                }
                                
                                response = requests.get(self.URL, params=params)
                                self.chunks_downloaded.sort(key=lambda x: x['piece_index'])
                                print(f"Downloaded pieces: {len(self.chunks_downloaded)}, duplicates: {self.duplicate}")
                                #print('sorted Downloaded:', self.chunks_downloaded, 'length:', len(self.chunks_downloaded))
                                print('number of pieces for each peer:', self.count)
                                for peer in self.peer_list:
                                    print("available chunks for peer with ID:", peer.ID," ", peer.available_chunks)
                                
                                time.sleep(1)
        
                        else:
                            #print("REC: Received duplicate piece message")
                            with self.duplicate_lock:
                                self.duplicate += 1
                            
                            #break
                    else:
                        print("REC: Received unknown message", message)
                except Exception as e:
                    with peer_obj.live_lock:
                        peer_obj.is_alive = False
                    print(f"Error receiving message: {e}")
                    break

        print("REC: Receive closed for peer with ID:", peer_obj.ID,'\n')